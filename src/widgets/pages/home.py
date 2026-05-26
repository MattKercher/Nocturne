# home.py

from gi.repository import Gtk, Adw, GLib, Gst, Gio
from ...integrations import get_current_integration
from ..album import AlbumButton
from ..artist import ArtistButton
from ..playlist import PlaylistButton
from ..song import SongSmallRow
import threading

@Gtk.Template(resource_path='/com/jeffser/Nocturne/pages/home.ui')
class HomePage(Adw.NavigationPage):
    __gtype_name__ = 'NocturneHomePage'

    main_stack = Gtk.Template.Child()
    song_wrapbox = Gtk.Template.Child()
    album_carousel = Gtk.Template.Child()
    artist_carousel = Gtk.Template.Child()
    playlist_carousel = Gtk.Template.Child()

    def __init__(self):
        super().__init__()

        self.song_wrapbox.set_header(
            label=_("Songs"),
            icon_name="music-note-symbolic",
            page_tag="songs-all"
        )
        self.song_wrapbox.list_el.set_margin_start(10)
        self.song_wrapbox.list_el.set_margin_end(10)
        self.song_wrapbox.list_el.set_justify(Adw.JustifyMode.FILL)
        self.song_wrapbox.list_el.set_justify_last_line(True)
        self.song_wrapbox.list_el.set_child_spacing(5)
        self.song_wrapbox.list_el.set_line_spacing(5)
        self.album_carousel.set_header(
            label=_("Albums"),
            icon_name="music-queue-symbolic",
            page_tag="albums-all"
        )
        self.artist_carousel.set_header(
            label=_("Artists"),
            icon_name="music-artist-symbolic",
            page_tag="artists"
        )
        self.playlist_carousel.set_header(
            label=_("Playlists"),
            icon_name="playlist-symbolic",
            page_tag="playlists"
        )

    def reload(self):
        # call in different thread
        integration = get_current_integration()
        settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
        max_songs = settings.get_value('n-songs-home').unpack()
        max_albums = settings.get_value('n-albums-home').unpack()
        max_artists = settings.get_value('n-artists-home').unpack()
        max_playlists = settings.get_value('n-playlists-home').unpack()

        # -- Songs --
        songs = integration.getRandomSongs(size=max_songs) if max_songs > 0 else []
        threading.Thread(
            target=self.song_wrapbox.set_widgets,
            args=([SongSmallRow(id) for id in songs],),
            daemon=True
        ).start()

        # -- Albums --
        albums = integration.getAlbumList(size=max_albums) if max_albums > 0 else []
        threading.Thread(
            target=self.album_carousel.set_widgets,
            args=([AlbumButton(id) for id in albums],),
            daemon=True
        ).start()

        # -- Artists --
        artists = integration.getArtists(size=max_artists) if max_artists > 0 else []
        threading.Thread(
            target=self.artist_carousel.set_widgets,
            args=([ArtistButton(id) for id in artists],),
            daemon=True
        ).start()

        # -- Playlists --
        playlists = integration.getPlaylists()[:max_playlists]
        threading.Thread(
            target=self.playlist_carousel.set_widgets,
            args=([PlaylistButton(id) for id in playlists],),
            daemon=True
        ).start()

        n_elements = sum([len(s) for s in (songs, albums, artists, playlists)])
        GLib.idle_add(self.main_stack.set_visible_child_name, 'content' if n_elements > 0 else 'no-content')

    def reset(self):
        threading.Thread(target=self.song_wrapbox.set_widgets, args=([],), daemon=True).start()
        threading.Thread(target=self.album_carousel.set_widgets, args=([],), daemon=True).start()
        threading.Thread(target=self.artist_carousel.set_widgets, args=([],), daemon=True).start()
        threading.Thread(target=self.playlist_carousel.set_widgets, args=([],), daemon=True).start()
