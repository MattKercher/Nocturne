# jellyfin.py

from gi.repository import GLib, GObject, Gdk, Gio
from . import secret, models, local, sql_instance
from .base import Base
from ..constants import DOWNLOAD_QUEUE_DIR, DOWNLOADS_DIR, DOWNLOAD_MIME_MAP
import threading, os, platform, logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class Jellyfin(Base):
    __gtype_name__ = 'NocturneIntegrationJellyfin'

    login_page_metadata = {
        'icon-name': "jellyfin-symbolic",
        'title': "Jellyfin",
        'description': _("Connect to a Jellyfin server."),
        'entries': ["url", "user", "password", "trust-server"],
    }
    button_metadata = {
        'title': _("Jellyfin"),
        'subtitle': _("Use an existing Jellyfin instance")
    }
    limitations = ('no-edit-radio',)
    cache_actions = {
        'deleted-radios': []
    }

    sqlSchema = {
        'ratings': {
            'id': 'TEXT PRIMARY KEY',
            'rating': 'INTEGER DEFAULT 1'
        }
    }

    ongoing_requests = set()

    AUTH_HEADER = 'MediaBrowser Client="Nocturne", Device="{}", DeviceId="{}", Version="1.0.0"'.format(platform.node(), str(abs(hash(platform.node()))))

    url = GObject.Property(type=str, default="http://127.0.0.1:8096")

    # Loaded by API
    accessToken = GObject.Property(type=str)
    userId = GObject.Property(type=str)
    libraryId = GObject.Property(type=str)

    def get_base_header(self) -> dict:
        headers = {
            "Authorization": self.AUTH_HEADER,
            "Accept": "application/json"
        }
        if token := self.get_property('accessToken'):
            headers["Authorization"] += ', Token="{}"'.format(token)
        return headers

    def get_url(self, action:str, **keys) -> str:
        action = action.format(userId=self.get_property('userId'), **keys)
        return '{}/{}'.format(self.get_property('url').strip('/'), action)

    def make_request(self, action:str, json:dict={}, params:dict={}, mode:str="GET", action_keys:dict={}) -> dict:
        def request_job(url):
            try:
                if mode == 'GET':
                    response = self.session.get(
                        url,
                        params=params,
                        json=json,
                        headers=self.get_base_header(),
                        verify=not self.get_property('trustServer')
                    )
                elif mode == 'POST':
                    response = self.session.post(
                        url,
                        params=params,
                        json=json,
                        headers=self.get_base_header(),
                        verify=not self.get_property('trustServer')
                    )
                elif mode == 'DELETE':
                    response = self.session.delete(
                        url,
                        params=params,
                        json=json,
                        headers=self.get_base_header(),
                        verify=not self.get_property('trustServer')
                    )
                elif mode == 'RAWGET':
                    # Get without calling json()
                    response = self.session.get(
                        self.get_url(action, **action_keys),
                        params=params,
                        json=json,
                        headers=self.get_base_header(),
                        verify=not self.get_property('trustServer')
                    )
                    return response.status_code in (200, 201), response
                if response.status_code in (200, 201):
                    return True, response.json()
                elif response.status_code == 204:
                    return True, {'state': 'ok'}
            except Exception as e:
                logger.error(f"action error {action}: {e}")
            return False, {}
        action_url = self.get_url(action, **action_keys)
        request_id = '({}) {}?{}'.format(mode, action_url, urlencode(params))
        return self.cache_manager.get_result(request_id, request_job, action_url)

    def get_rating(self, model_id) -> int:
        conn, cursor = sql_instance.get_connection(self)
        cursor.execute("SELECT rating FROM ratings WHERE id = ?", (model_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0

    def start_instance(self) -> bool:
        return True

    def terminate_instance(self):
        pass

    def get_stream_url(self, song_id:str) -> str:
        if model := self.loaded_models.get(song_id):
            if radioStreamUrl := model.get_property('radioStreamUrl'):
                try:
                    with self.session.get(radioStreamUrl, stream=True, timeout=10) as r:
                        r.raise_for_status()
                        content_type = r.headers.get('Content-Type', '').lower()
                        if 'mpegurl' in content_type or 'text/plain' in content_type or 'octet-stream' in content_type:
                            # It is a playlist text file, extract url
                            for line in r.iter_lines(decode_unicode=True):
                                line = line.decode('utf-8')
                                if line and not line.startswith('#'):
                                    return line.strip()
                except:
                    pass
                return radioStreamUrl
            elif model.get_property('isExternalFile'):
                return 'file://{}'.format(model.get_property('path'))
        base_url = self.get_url('Audio/{}/stream'.format(song_id))
        max_bitrate = Gio.Settings(schema_id="com.jeffser.Nocturne").get_value('max-bitrate').unpack()
        if max_bitrate == 0:
            return '{}?static=true&api_key={}'.format(
                base_url,
                self.get_property('accessToken')
            )
        else:
            return '{}?static=true&audioBitrate={}&api_key={}'.format(
                base_url,
                max_bitrate*1000,
                self.get_property('accessToken')
            )

    def initiateQuickConnect(self) -> dict:
        return self.make_request(
            action='QuickConnect/Initiate',
            mode='POST',
        )

    def checkQuickConnect(self, secret_str:str) -> bool:
        response = self.make_request(
            action='QuickConnect/Connect',
            params={'secret': secret_str}
        )
        if response.get('Authenticated'):
            secret.store_password(response.get("Secret"))
            return True
        return False

    def getCoverArtBytes(self, model_id:str, size:int) -> bytes:
        try:
            url = self.get_url('Items/{id}/Images/Primary', id=model_id)
            if image_id := self.loaded_models.get(model_id).get_property('coverArt'):
                url = self.get_url('Items/{id}/Images/Primary?={tag_id}', id=model_id, tag_id=image_id)

            response = self.make_request(
                action='Items/{id}/Images/Primary',
                action_keys={'id': model_id},
                params={
                    'maxWidth': size,
                    'quality': 90
                },
                mode="RAWGET"
            )
            response.raise_for_status()
            return response.content
        except Exception as e:
            logger.error(f"can't get image from {model_id}: {e}")
        return b''

    def updateCoverArt(self, model_id:str=''):
        if model := self.loaded_models.get(model_id):
            if isinstance(model, models.Song) and model.get_property('isExternalFile'):
                local.Local.updateCoverArt(self, model_id)
                return

            sizes = {
                'gdkPaintableBig': 720,
                'gdkPaintable': 240
            }
            for property_name, size in sizes.items():
                if not model.get_property(property_name):
                    raw_bytes = self.get_cache_image(model_id, size)
                    save_cache = not raw_bytes
                    if not raw_bytes:
                        raw_bytes = self.getCoverArtBytes(model_id, size)
                        if not raw_bytes and isinstance(model, models.Song):
                            raw_bytes = self.getCoverArtBytes(model.get_property('albumId'), size)
                            if raw_bytes:
                                model.set_property('coverArt', model.get_property('albumId')) # For getCoverArtUrl
                    if raw_bytes:
                        try:
                            gbytes = GLib.Bytes.new(raw_bytes)
                            texture = Gdk.Texture.new_from_bytes(gbytes)
                            model.set_property(property_name, texture)
                            if save_cache:
                                self.save_cache_image(model_id, raw_bytes)
                        except Exception as e:
                            logger.error(f"can't convert image from {model_id} (size {size}): {e}")

    def getCoverArtUrl(self, model_id) -> str:
        if model := self.loaded_models.get(model_id):
            if isinstance(model, models.Song) and model.get_property('isExternalFile'):
                return ""
            params = {
                'maxWidth': 240,
                'quality': 90
            }
            if token := self.get_property('accessToken'):
                params['api_key'] = token
            return '{}?{}'.format(self.get_url('Items/{id}/Images/Primary', id=model.get_property('coverArt') or model_id), urlencode(params))
        return ""

    def ping(self) -> dict:
        self.set_property('accessToken', "")
        self.set_property('userId', "")
        response = self.make_request(
            action='Users/AuthenticateWithQuickConnect',
            json={
                "Secret": secret.get_plain_password()
            },
            mode='POST'
        )
        self.set_property('accessToken', response.get('AccessToken'))
        self.set_property('userId', response.get('User', {}).get('Id'))
        if self.get_property("accessToken") and self.get_property("userId"):
            self.set_property("user", response.get('User', {}).get('Name'))
        else:
            response = self.make_request(
                action='Users/AuthenticateByName',
                json={
                    'Username': self.get_property('user'),
                    'Pw': secret.get_plain_password()
                },
                mode='POST'
            )
            self.set_property('accessToken', response.get('AccessToken'))
            self.set_property('userId', response.get('User', {}).get('Id'))
        if self.get_property('accessToken') and self.get_property('userId'):
            libraries = self.make_request(
                action='Users/{userId}/Views',
                mode='GET'
            ).get("Items", [])
            for library in libraries:
                if library.get("CollectionType") == "music":
                    self.set_property('libraryId', library.get("Id"))
                    break
            return super().ping()
        return {
            'status': 'error',
            'message': _('Could not log in')
        }

    def getAlbumList(self, list_type:str="recent", size:int=10, offset:int=0) -> list:
        params = {
            "IncludeItemTypes": "MusicAlbum",
            "Recursive": "true",
            "Limit": size,
            "StartIndex": offset,
            "Fields": "ArtistItems,IsFavorite",
            "ParentId": self.get_property("libraryId")
        }
        if list_type == "random":
            params["SortBy"] = "Random"
        elif list_type == "newest":
            params["SortBy"] = "DateCreated"
            params["SortOrder"] = "Descending"
        elif list_type == "frequent":
            params["SortBy"] = "PlayCount"
            params["SortOrder"] = "Descending"
        elif list_type == "recent":
            params["SortBy"] = "DatePlayed"
            params["SortOrder"] = "Descending"
        elif list_type == "starred":
            params["Filters"] = "IsFavorite"

        albums = self.make_request(
            action='Users/{userId}/Items',
            mode='GET',
            params=params
        ).get('Items', [])
        id_list = []
        for album in albums:
            if album.get("Id"):
                self.verifyAlbum(album.get("Id"), album_object=album, lite=True)
                id_list.append(album.get("Id"))
        return id_list

    def getArtists(self, size:int=10) -> list:
        response = self.make_request(
            action='Artists/AlbumArtists',
            mode='GET',
            params={
                "Limit": size,
                "Recursive": "true",
                "Fields": "Overview,SimilarItems,UserData",
                "SortBy": "Random",
                "SortOrder": "Ascending",
                "ParentId": self.get_property("libraryId")
            }
        )
        id_list = []
        for artist in response.get('Items', []):
            if artist.get("Id"):
                self.verifyArtist(artist.get("Id"), artist_object=artist)
                id_list.append(artist.get("Id"))
        return id_list

    def getPlaylists(self) -> list:
        response = self.make_request(
            action='Users/{userId}/Items',
            mode='GET',
            params={
                "IncludeItemTypes": "Playlist",
                "Recursive": "true",
                "Fields": "None"
            }
        )
        id_list = []
        for playlist in response.get('Items', []):
            if playlist.get("Id"):
                self.verifyPlaylist(playlist.get("Id"), playlist_object=playlist, lite=True)
                id_list.append(playlist.get("Id"))
        return id_list

    def getStarredSongs(self) -> list:
        song_list = []
        songs = self.make_request(
            action="Users/{userId}/Items",
            mode="GET",
            params={
                "IncludeItemTypes": "Audio",
                "Recursive": "true",
                "Fields": "Id",
                "Filters": "IsFavorite",
                "ParentId": self.get_property("libraryId")
            }
        ).get("Items", [])

        return [song.get("Id") for song in songs]

    def verifyArtist(self, model_id:str, artist_object:models.Artist=None, lite:bool=False, force_update:bool=False, use_threading:bool=True):
        def run():
            artist = artist_object
            if artist is None:
                artist = self.make_request(
                    action='Users/{userId}/Items/{id}',
                    action_keys={"id": model_id},
                    mode="GET"
                )

            if artist.get("Id"):
                params={
                    "AlbumArtistIds": [model_id],
                    "IncludeItemTypes": "MusicAlbum",
                    "Recursive": "true",
                    "SortBy": "PremiereDate"
                }
                if lite:
                    params["Limit"]=0
                albums_request = self.make_request(
                    action='Users/{userId}/Items',
                    mode="GET",
                    params=params
                )
                albums = albums_request.get("Items", [])

                similar = []
                if not lite: #Reduce request size
                    similar = self.make_request(
                        action='/Items/{id}/Similar?userId={userId}',
                        action_keys={"id": model_id},
                        params={"limit": 12},
                        mode="GET"
                    ).get("Items", [])

                self.loaded_models.get(model_id).update_data(
                    id=artist.get("Id"),
                    name=artist.get("Name"),
                    coverArt=artist.get('ImageTags', {}).get('Primary', ''),
                    albumCount=albums_request.get("TotalRecordCount"),
                    album=[{"id": alb.get("Id"), "name": alb.get("Name")} for alb in albums],
                    starred=artist.get("UserData", {}).get("IsFavorite", False),
                    biography=artist.get("Overview", ""),
                    similarArtist=[{"id": sim.get("Id"), "name": sim.get("Name")} for sim in similar],
                    #similarArtists=[{"id": art.get("Id"), "name": art.get("Name")} for art in artist.get("SimilarItems", [])],
                    userRating=self.get_rating(artist.get("Id"))
                )
                if(artist.get('ImageTags', {}).get('Primary', '')):
                    threading.Thread(target=self.updateCoverArt, kwargs={"model_id": model_id}, daemon=True).start()
            elif model_id in self.loaded_models:
                del self.loaded_models[model_id]
            self.ongoing_requests.remove(model_id)

        if not model_id or not model_id.strip():
            logger.warning ("Empty Artist model_id, aborting.")
            return

        if model_id not in self.loaded_models or force_update:
            # Prevent repeated requests
            if model_id in self.ongoing_requests and not force_update:
                logger.debug(f"GET request for Artist: {model_id} is ongoing, aborting.")
                return
            self.ongoing_requests.add(model_id)

            if model_id not in self.loaded_models:
                self.loaded_models[model_id] = models.Artist(id=model_id)
            if use_threading:
                threading.Thread(target=run, daemon=True).start()
            else:
                run()

        #threading.Thread(target=self.updateCoverArt, args=(model_id,), daemon=True).start()

    def verifyAlbum(self, model_id:str, album_object:models.Album=None, force_update:bool=False, lite:bool=False, use_threading:bool=True):
        def run():
            album = album_object
            if album is None:
                album = self.make_request(
                    action='Users/{userId}/Items/{id}',
                    action_keys={"id": model_id},
                    mode="GET"
                )

            if album.get("Id"):
                songs=[]
                if not lite:
                    songs = self.make_request(
                        action='Users/{userId}/Items',
                        mode="GET",
                        params={
                            "ParentId": model_id,
                            "IncludeItemTypes": "Audio",
                            "Recursive": "true",
                            "Fields": "RunTimeTicks,IndexNumber,ParentIndexNumber,ProductionYear",
                            "SortBy": "ParentIndexNumber,IndexNumber",
                            "SortOrder": "Ascending"
                        }
                    ).get("Items", [])

                duration = int(sum(song.get("RunTimeTicks", 0) for song in songs) / 10000000)

                for i, song in enumerate(songs):
                    if model := self.loaded_models.get(song.get("Id")):
                        model.update_data(track=song.get("IndexNumber") or i)

                self.loaded_models.get(model_id).update_data(
                    id=album.get("Id"),
                    name=album.get("Name"),
                    artist=album.get("AlbumArtist"),
                    artistId=album.get("ArtistItems", [{}])[0].get("Id") if album.get("ArtistItems") else None,
                    coverArt=album.get('ImageTags', {}).get('Primary', ''),
                    songCount=len(songs),
                    duration=duration,
                    artists=[{"id": art.get("Id"), "name": art.get("Name")} for art in album.get("ArtistItems", [])],
                    song=[{"id": song.get("Id"), "name": song.get("Name")} for song in songs],
                    starred=album.get("UserData", {}).get("IsFavorite", False),
                    userRating=self.get_rating(album.get("Id")),
                    year=album.get("ProductionYear", 0)
                )
                if(album.get('ImageTags', {}).get('Primary', '')):
                    threading.Thread(target=self.updateCoverArt, kwargs={"model_id": model_id}, daemon=True).start()
            elif model_id in self.loaded_models:
                del self.loaded_models[model_id]
            self.ongoing_requests.remove(model_id)

        if not model_id or not model_id.strip():
            logger.warning("Empty Album model_id, aborting.")
            return

        if model_id not in self.loaded_models or force_update:
            # Prevent repeated requests
            if model_id in self.ongoing_requests and not force_update:
                logger.debug(f"GET request for Album: {model_id} is ongoing, aborting.")
                return
            self.ongoing_requests.add(model_id)

            if model_id not in self.loaded_models:
                self.loaded_models[model_id] = models.Album(id=model_id)
            if use_threading:
                threading.Thread(target=run, daemon=True).start()
            else:
                run()

        #threading.Thread(target=self.updateCoverArt, args=(model_id,), daemon=True).start()

    def verifyPlaylist(self, model_id:str, playlist_object:models.Playlist=None, lite:bool=False, force_update:bool=False, use_threading:bool=True):
        def run():
            playlist = playlist_object
            if playlist is None:
                playlist = self.make_request(
                    action='Users/{userId}/Items/{id}',
                    action_keys={"id": model_id},
                    mode="GET"
                )
            if playlist.get("Id"):
                params = {
                    "UserId": self.get_property("userId"),
                    "Fields": "RunTimeTicks"
                }
                if(lite):
                    params["Limit"]=0,

                songs_response = self.make_request(
                    action='Playlists/{id}/Items',
                    action_keys={"id": model_id},
                    mode="GET",
                    params=params
                )#.get("Items", [])

                songs = songs_response.get("Items", [])
                duration = int(sum(song.get("RunTimeTicks", 0) for song in songs) / 10000000)

                self.loaded_models.get(model_id).update_data(
                    id=playlist.get("Id"),
                    name=playlist.get("Name"),
                    coverArt=playlist.get('ImageTags', {}).get('Primary', ''),
                    songCount=songs_response.get("TotalRecordCount"),
                    duration=duration,
                    entry=[{"id": song.get("Id"), "name": song.get("Name")} for song in songs]
                )
                if(playlist.get('ImageTags', {}).get('Primary', '')):
                    threading.Thread(target=self.updateCoverArt, kwargs={"model_id": model_id}, daemon=True).start()
            elif model_id in self.loaded_models:
                del self.loaded_models[model_id]
            self.ongoing_requests.remove(model_id)

        if not model_id or not model_id.strip():
            logger.warning("Empty Playlist model_id, aborting.")
            return

        if model_id not in self.loaded_models or force_update:
            # Prevent repeated requests
            if model_id in self.ongoing_requests and not force_update:
                logger.debug(f"GET request for Playlist: {model_id} is ongoing, aborting.")
                return
            self.ongoing_requests.add(model_id)

            if model_id not in self.loaded_models:
                self.loaded_models[model_id] = models.Playlist(id=model_id)
            if use_threading:
                threading.Thread(target=run, daemon=True).start()
            else:
                run()

        #threading.Thread(target=self.updateCoverArt, args=(model_id,), daemon=True).start()

    def verifySong(self, model_id:str, song_object:models.Song=None, force_update:bool=False, use_threading:bool=True):
        def run():
            song = song_object
            if song is None:
                params = {
                    "Fields": "ArtistItems,AlbumId,RunTimeTicks,UserData,IndexNumber,ParentIndexNumber"
                }
                song = self.make_request(
                    action='Users/{userId}/Items/{id}',
                    action_keys={"id": model_id},
                    mode='GET',
                    params=params
                )

            if song.get("Id"):
                duration = int(song.get("RunTimeTicks", 0) / 10000000)
                self.loaded_models.get(model_id).update_data(
                    id=song.get("Id"),
                    title=song.get("Name"),
                    album=song.get("Album"),
                    albumId=song.get("AlbumId"),
                    artist=song.get("AlbumArtist"),
                    artistId=(song.get("ArtistItems") or [{}])[0].get("Id"),
                    coverArt=song.get('ImageTags', {}).get('Primary', ''),
                    duration=duration,
                    artists=[{"id": art.get("Id"), "name": art.get("Name")} for art in song.get("ArtistItems", [])],
                    starred=song.get("UserData", {}).get("IsFavorite", False),
                    track=song.get("IndexNumber") or 0,
                    discNumber=song.get("ParentIndexNumber") or 0,
                    albumGain=song.get("AlbumNormalizationGain", song.get("NormalizationGain")) or 0.0,
                    trackGain=song.get("NormalizationGain") or 0.0,
                    userRating=self.get_rating(model_id)
                )
                if(song.get('ImageTags', {}).get('Primary', '')):
                    threading.Thread(target=self.updateCoverArt, kwargs={"model_id": model_id}, daemon=True).start()
            elif model_id in self.loaded_models:
                self.loaded_models.get(model_id).set_property('deleted', True)
                del self.loaded_models[model_id]
            self.ongoing_requests.remove(model_id)

        if not model_id or not model_id.strip():
            logger.warning ("Empty Song model_id, aborting.")
            return

        if model_id not in self.loaded_models or force_update:
            # Prevent repeated requests
            if model_id in self.ongoing_requests and not force_update:
                logger.debug(f"GET request for Song: {model_id} is ongoing, aborting.")
                return
            self.ongoing_requests.add(model_id)

            if model_id not in self.loaded_models:
                self.loaded_models[model_id] = models.Song(id=model_id)
            if use_threading:
                threading.Thread(target=run, daemon=True).start()
            else:
                run()

        #threading.Thread(target=self.updateCoverArt, args=(model_id,), daemon=True).start()

    def star(self, model_id:str) -> bool:
        response = self.make_request(
            action='Users/{userId}/FavoriteItems/{id}',
            action_keys={"id": model_id},
            mode='POST'
        )
        return response.get('IsFavorite', False)

    def unstar(self, model_id:str) -> bool:
        response = self.make_request(
            action='Users/{userId}/FavoriteItems/{id}',
            action_keys={"id": model_id},
            mode='DELETE'
        )
        return not response.get('IsFavorite', False)

    def getPlayQueue(self) -> tuple:
        queue_dict = self.open_json('queue.json')
        song_list = [model_id for model_id in queue_dict.get('id', [])]
        current = queue_dict.get('current', "")
        if current not in song_list:
            if len(song_list) > 0:
                current = song_list[0]
            else:
                current = ""

        return current, song_list

    def savePlayQueue(self, id_list:list, current:str, position:int) -> bool:
        final_id_list = []
        for model_id in id_list:
            if model := self.loaded_models.get(model_id):
                if not model.isExternalFile:
                    final_id_list.append(model_id)

        if current not in final_id_list:
            if len(final_id_list) > 0:
                current = final_id_list[0]
            else:
                current = ""

        queue_dict = {
            'id': final_id_list,
            'current': current,
            'position': position
        }
        self.save_json('queue.json', queue_dict)
        return True

    def getSimilarSongs(self, model_id:str, count:int=20) -> list:
        artist_songs = self.make_request(
            action='Users/{userId}/Items',
            mode="GET",
            params={
                "ArtistIds": model_id,
                "IncludeItemTypes": "Audio",
                "Recursive": "true",
                "Limit": 1,
            }
        ).get('Items', [])

        if len(artist_songs) == 0:
            return []

        songs = self.make_request(
            action='Items/{id}/Similar',
            action_keys={"id": artist_songs[0].get("Id")},
            mode='GET',
            params={
                "UserId": self.get_property("userId"),
                "Limit": count,
                "IncludeItemTypes": "Audio",
                "Fields": "ArtistItems,RunTimeTicks,UserData"
            }
        ).get("Items", [])

        id_list = []
        for song in songs:
            if song.get("Id"):
                self.verifySong(song.get("Id"), song)
                id_list.append(song.get("Id"))
        return id_list

    def getRandomSongs(self, size:int=20) -> list:
        songs = self.make_request(
            action='Users/{userId}/Items',
            mode="GET",
            params={
                "IncludeItemTypes": "Audio",
                "Recursive": "true",
                "Fields": "RunTimeTicks,UserData,ArtistItems",
                "Limit": size,
                "SortBy": "Random",
                "MediaTypes": "Audio",
                "ParentId":self.get_property("libraryId")
            }
        ).get('Items', [])

        id_list = []
        for song in songs:
            if song.get("Id"):
                self.verifySong(song.get("Id"), song_object=song)
                id_list.append(song.get("Id"))
        return id_list

    def getLyrics(self, songId:str) -> dict:
        result = self.make_request(
            action='Audio/{id}/Lyrics',
            action_keys={'id': songId},
            mode='GET'
        )
        isSynced = bool(result.get('Lyrics', [{}])[0].get('Start'))
        if isSynced:
            lines = []
            for line in result.get('Lyrics', []):
                lines.append({
                    'content': line.get('Text'),
                    'ms': line.get('Start') / 10000
                })
            return {
                'type': 'lrc',
                'content': lines
            }
        else:
            text = '\n'.join([line.get('Text') for line in result.get('Lyrics', [])])
            if text:
                return {
                    'type': 'plain',
                    'content': text
                }
        return {'type': 'not-found'}

    def __fetch_type(self, item_type:str, query:str, limit:int=5, offset:int=0, fields:str=""):
        # Method exclusive to Jellyfin, helper for searches
        items = []
        if item_type == "MusicArtist":
            items = self.make_request(
                action='Artists/AlbumArtists',
                mode="GET",
                params={
                    "userId": self.get_property("userId"),
                    "parentId": self.get_property("libraryId"),
                    "SearchTerm": query,
                    "Recursive": "true",
                    "Limit": limit,
                    "StartIndex": offset,
                    "Fields": fields
                }
            ).get('Items', [])
        else:
            params = {
                "SearchTerm": query,
                "IncludeItemTypes": item_type,
                "Recursive": "true",
                "Limit": limit,
                "StartIndex": offset,
                "Fields": fields
            }
            if item_type != "Playlist":
                params["ParentId"] = self.get_property("libraryId")
            items = self.make_request(
                action='Users/{userId}/Items',
                mode="GET",
                params=params
            ).get('Items', [])

        for item in items:
            if item_type == "MusicArtist":
                self.verifyArtist(item.get("Id"), artist_object=item, lite=True)
            elif item_type == "MusicAlbum":
                self.verifyAlbum(item.get("Id"), album_object=item)
            elif item_type == "Audio":
                self.verifySong(item.get("Id"), song_object=item)
            elif item_type == "Playlist":
                self.verifyPlaylist(item.get("Id"), playlist_object=item)
        return items

    def search(self, query:str, artistCount:int=0, artistOffset:int=0, albumCount:int=0, albumOffset:int=0, songCount:int=0, songOffset:int=0, playlistCount:int=0, playlistOffset:int=0) -> dict:
        return {
            'artist': [item.get("Id") for item in self.__fetch_type("MusicArtist", query, artistCount, artistOffset)],
            'album': [item.get("Id") for item in self.__fetch_type("MusicAlbum", query, albumCount, albumOffset)],
            'song': [item.get("Id") for item in self.__fetch_type("Audio", query, songCount, songOffset)],
            'playlist': [item.get("Id") for item in self.__fetch_type("Playlist", query, playlistCount, playlistOffset)]
        }

    def systemSearch(self, query:str) -> dict:
        results = {}

        # Artists
        for artist in self.__fetch_type('MusicArtist', query):
            icon_bytes = self.getCoverArtBytes(artist.get('Id'), 128)
            results[artist.get('Id')] = {
                'display': GLib.Variant('s', artist.get('Name')),
                'type': GLib.Variant('s', 'artist'),
                'icon': GLib.Variant('ay', bytearray(icon_bytes))
            }

        # Albums
        for album in self.__fetch_type('MusicAlbum', query):
            if artist := album.get('AlbumArtist'):
                display_name = '{} • {}'.format(album.get('Name'), artist)
            else:
                display_name = album.get('Name')
            icon_bytes = self.getCoverArtBytes(album.get('Id'), 128)
            results[album.get('Id')] = {
                'display': GLib.Variant('s', display_name),
                'type': GLib.Variant('s', 'album'),
                'icon': GLib.Variant('ay', bytearray(icon_bytes))
            }

        # Songs
        for song in self.__fetch_type('Audio', query):
            if artist := song.get('AlbumArtist'):
                display_name = '{} • {}'.format(song.get('Name'), artist)
            else:
                display_name = song.get('Name')
            icon_bytes = self.getCoverArtBytes(song.get('Id'), 128)
            results[song.get('Id')] = {
                'display': GLib.Variant('s', display_name),
                'type': GLib.Variant('s', 'song'),
                'icon': GLib.Variant('ay', bytearray(icon_bytes))
            }

        # Playlist
        for playlist in self.__fetch_type('Playlist', query):
            icon_bytes = self.getCoverArtBytes(playlist.get('Id'), 128)
            results[playlist.get('Id')] = {
                'display': GLib.Variant('s', playlist.get('Name')),
                'type': GLib.Variant('s', 'playlist'),
                'icon': GLib.Variant('ay', bytearray(icon_bytes))
            }

        return results

    def getInternetRadioStations(self) -> list:
        radios = self.make_request(
            action='LiveTv/Channels',
            mode='GET',
            params={
                "userId": self.get_property("userId"),
                "type": "Radio"
            }
        ).get('Items', [])

        id_list = []
        for radio in radios:
            if radio.get("Id") not in self.cache_actions.get('deleted-radios'):
                radio_model = models.Song(
                    id=radio.get("Id"),
                    title=radio.get("Name"),
                    duration=-1
                )
                self.loaded_models[radio.get("Id")] = radio_model

                raw_url = None
                radio_metadata = test_radio = self.make_request(
                    action='Items/{id}/PlaybackInfo',
                    action_keys={'id': radio.get('Id')},
                    params={
                        "fields": "Path",
                        "userId": self.get_property("userId")
                    }
                ).get('MediaSources', [])
                if len(radio_metadata) > 0:
                    raw_url = radio_metadata[0].get('Path')
                if not raw_url:
                    raw_url = self.get_stream_url(radio.get("Id"))
                self.loaded_models.get(radio.get("Id")).set_property("radioStreamUrl", raw_url)

                id_list.append(radio.get("Id"))
        return id_list

    def createInternetRadioStation(self, name:str, radioStreamUrl:str) -> bool:
        radio = self.make_request(
            action='LiveTv/TunerHosts',
            mode='POST',
            json={
                "Url": radioStreamUrl,
                "Type": "M3U",
                "FriendlyName": name
            }
        )
        if radio.get('Id'):
            self.loaded_models[radio.get("Id")] = models.Song(
                id=radio.get("Id"),
                title=radio.get("FriendlyName"),
                duration=-1,
                radioStreamUrl=radioStreamUrl
            )
            return True
        return False

    def deleteInternetRadioStation(self, model_id:str) -> bool:
        response = self.make_request(
            action='LiveTv/TunerHosts',
            mode='DELETE',
            params={
                "id": model_id
            }
        )
        if response.get('state') == 'ok':
            self.cache_actions['deleted-radios'].append(model_id)
            return True
        return False

    def createPlaylist(self, name:str=None, playlistId:str=None, songId:list=[]) -> str:
        if playlistId:
            #TODO update name
            if self.updatePlaylist(playlistId=playlistId, songIdToAdd=songId):
                return playlistId
            else:
                return ''
        response = self.make_request(
            action='Playlists',
            mode="POST",
            params={
                "UserId": self.get_property("userId"),
                "MediaType": "Audio"
            },
            json={
                "Name": name,
                "Ids": ",".join(songId)
            }
        )
        return response.get("Id", "")

    def updatePlaylist(self, playlistId:str, songIdToAdd:list=[], songIndexToRemove:list=[]) -> bool:
        if songIndexToRemove:
            current_items = self.make_request(
                action='Playlists/{id}/Items',
                action_keys={"id": playlistId},
                mode="GET",
                params={
                    "UserId": self.get_property("userId")
                }
            ).get("Items", [])

            entry_ids_to_remove = []
            for index in songIndexToRemove:
                index = int(index)
                if 0 <= index < len(current_items):
                    entry_ids_to_remove.append(current_items[index].get("PlaylistItemId"))

            if entry_ids_to_remove:
                self.make_request(
                    action='Playlists/{id}/Items',
                    action_keys={"id": playlistId},
                    mode="DELETE",
                    params={
                        "EntryIds": ",".join(entry_ids_to_remove)
                    }
                )

        if songIdToAdd:
            self.make_request(
                action="Playlists/{id}/Items",
                action_keys={"id": playlistId},
                mode="POST",
                params={
                    "Ids": ",".join(songIdToAdd),
                    "UserId": self.get_property("userId")
                }
            )

        return True

    def deletePlaylist(self, model_id:str) -> bool:
        response = self.make_request(
            action='Items/{id}',
            action_keys={'id': model_id},
            mode="DELETE"
        )
        return response.get("state") == "ok"

    def setRating(self, model_id:str, rating:int=0) -> bool:
        conn, cursor = sql_instance.get_connection(self)
        if rating == 0:
            cursor.execute("DELETE FROM ratings WHERE id = ?", (model_id,))
        else:
            query = """
            INSERT INTO ratings (id, rating)
            VALUES (?, ?)
            ON CONFLICT (id) DO UPDATE SET
                rating = excluded.rating
            """
            cursor.execute(query, (model_id, rating))
        conn.commit()
        conn.close()
        return True

    def getTopSongs(self, artist_id:str, count:int=10) -> list:
        songs = self.make_request(
            action='Users/{userId}/Items',
            mode='GET',
            params={
                'ArtistIds': artist_id,
                'IncludeItemTypes': 'Audio',
                'SortBy': 'PlayCount',
                'SortOrder': 'Descending',
                'Limit': count,
                'Recursive': 'true',
                'ParentId': self.get_property("libraryId")
            }
        ).get('Items', [])
        return [song.get('Id') for song in songs if song.get('Id')]

    def downloadSong(self, model_id:str, file_title:str, progress_callback:callable):
        try:
            with self.session.get(self.get_url('Items/{id}/Download', id=model_id), headers=self.get_base_header(), stream=True) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded_size = 0
                extension = DOWNLOAD_MIME_MAP.get(r.headers.get('Content-Type'), '.mp3')
                file_name = '{}{}'.format(file_title, extension)
                file_path = os.path.join(DOWNLOAD_QUEUE_DIR, file_name)
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            if total_size > 0:
                                progress_callback(downloaded_size / total_size)
                os.replace(file_path, os.path.join(DOWNLOADS_DIR, file_name))
        except Exception as e:
            logger.error(f"can't download song {model_id}: {e}")

    def getSongDetails(self, model_id:str) -> models.SongDetails:
        song = self.make_request(
            action='Users/{userId}/Items/{id}',
            action_keys={'id': model_id},
            mode='GET',
            params={
                'fields': 'MediaSources,Genres,ArtistItems,Path,ProductionYear,Taglines'
            }
        )
        # Limitations:
        # - no bpm
        return models.SongDetails(
            id=model_id,
            title=song.get('Name'),
            album=song.get('Album'),
            albumId=song.get('AlbumId'),
            artist=song.get('Artists')[0] if song.get('Artists') else "",
            artistId=song.get('ArtistItems')[0].get('Id', '') if song.get('ArtistItems') else "",
            musicBrainzId=song.get("ProviderIds", {}).get("MusicBrainzTrack") or "",
            track=song.get('IndexNumber', 0),
            year=song.get('ProductionYear', 0),
            size=song.get('MediaSources', [{}])[0].get('Size', 0),
            suffix=song.get('MediaSources', [{}])[0].get('Container', _("Unknown")),
            starred=song.get('UserData', {}).get('IsFavorite', False),
            duration=song.get('RunTimeTicks', 1) / 10_000_000,
            bitRate=song.get('MediaSources', [{}])[0].get('Bitrate', 1) / 1000,
            bitDepth=song.get('MediaSources', [{}])[0].get('MediaStreams', [{}])[0].get('BitDepth', 0),
            samplingRate=song.get('MediaSources', [{}])[0].get('MediaStreams', [{}])[0].get('SampleRate', 1),
            path=song.get('Path'),
            discNumber=song.get('ParentIndexNumber', 0),
            genres=[{'name': genre} for genre in song.get('Genres', [])],
            artists=[{'name': art.get('Name'), 'id': art.get('Id')} for art in song.get('ArtistItems', [])],
            trackGain=song.get('NormalizationGain', 0.0),
            albumGain=song.get('NormalizationGain', 0.0)
        )


    def getServerInformation(self) -> dict:
        server_information = {
            'link': self.get_property('url').strip('/'),
            'username': self.get_property('user').title()
        }
        try:
            response = self.make_request(
                action='Users/{userId}/Images/Primary',
                params={
                    "maxWidth": 240,
                    "quality": 90
                },
                mode='RAWGET'
            )
            response_bytes = response.content if response.status_code in (200, 201) else b''
            if response_bytes and len(response_bytes) > 0:
                gbytes = GLib.Bytes.new(response_bytes)
                server_information['picture'] = Gdk.Texture.new_from_bytes(gbytes)
        except Exception as e:
            logger.error(f"can't get server information: {e}")

        try:
            info = self.make_request(
                action="System/Info",
                mode="GET"
            )
            server_information["title"] = "{} {}".format(info.get("ServerName"), info.get("Version"))
        except Exception as e:
            logger.error(f"can't get server information: {e}")

        return server_information
