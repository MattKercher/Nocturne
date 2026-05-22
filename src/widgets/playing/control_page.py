# control_page.py

from gi.repository import Gtk, Adw, Gdk, GLib, GObject, Gst, Gio
from ...integrations import get_current_integration
from ...constants import get_display_time
import threading, random, io, os, glob
from urllib.parse import urlparse
from .player import Player

@Gtk.Template(resource_path='/com/jeffser/Nocturne/playing/control_page.ui')
class PlayingControlPage(Adw.NavigationPage):
    __gtype_name__ = 'NocturnePlayingControlPage'

    header_bar = Gtk.Template.Child()
    spectrum_el = Gtk.Template.Child()
    cover_el = Gtk.Template.Child()
    title_el = Gtk.Template.Child()
    radio_homepage_el = Gtk.Template.Child()
    artist_el = Gtk.Template.Child()
    album_el = Gtk.Template.Child()
    progress_el = Gtk.Template.Child()
    positive_progress_el = Gtk.Template.Child()
    negative_progress_el = Gtk.Template.Child()
    star_el = Gtk.Template.Child()
    show_sidebar_el = Gtk.Template.Child()
    state_stack_el = Gtk.Template.Child()
    rating_container = Gtk.Template.Child()
    song_connections = {
        'songId': '',
        'connections': []
    }

    def setup(self):
        integration = get_current_integration()
        integration.connect_to_model('currentSong', 'positionSeconds', self.update_position)
        integration.connect_to_model('currentSong', 'buttonState', self.state_stack_el.set_visible_child_name)
        integration.connect_to_model('currentSong', 'songId', self.song_changed)
        integration.connect_to_model('currentSong', 'displaySongTitle', self.display_title_changed)
        integration.connect_to_model('currentSong', 'displaySongArtist', self.display_artist_changed)
        self.spectrum_el.setup()
        self.setup_sidebar_button_connection()
        if stack := self.get_ancestor(Gtk.Stack):
            GLib.idle_add(stack.get_parent().set_overflow, Gtk.Overflow.HIDDEN)
            if stack2 := stack.get_parent().get_parent():
                GLib.idle_add(stack2.get_parent().set_overflow, Gtk.Overflow.HIDDEN)

    def update_position(self, positionSeconds:int):
        integration = get_current_integration()
        current_song = integration.loaded_models.get('currentSong')
        if current_song:
            song = integration.loaded_models.get(current_song.get_property('songId'))
            if song:
                label_positive = get_display_time(positionSeconds)
                label_negative = get_display_time(song.get_property('duration') - positionSeconds)
                self.positive_progress_el.set_label(label_positive)
                self.negative_progress_el.set_label('-{}'.format(label_negative))
                if not integration.loaded_models.get('currentSong').get_property('seeking'):
                    self.progress_el.get_adjustment().set_value(positionSeconds)

    def breakpoint_toggled(self, active:bool):
        self.show_sidebar_el.set_visible(active)
        if isinstance(self.get_parent(), Adw.NavigationView) and not self.get_parent().get_vhomogeneous():
            self.get_parent().set_vhomogeneous(True)

    def setup_sidebar_button_connection(self):
        self.get_root().breakpoint_el.connect('apply', lambda *_: self.breakpoint_toggled(True))
        self.get_root().breakpoint_el.connect('unapply', lambda *_: self.breakpoint_toggled(False))
        is_small = self.get_root().get_width() < 480
        self.breakpoint_toggled(is_small and self.get_root().get_width() > 0)

    @Gtk.Template.Callback()
    def progress_bar_changed(self, scale_el, scroll_type, value):
        value = scale_el.get_adjustment().get_value()
        integration = get_current_integration()
        integration.loaded_models.get('currentSong').set_property('seeking', True)
        def change_time(val):
            integration.loaded_models.get('currentSong').set_property('seeking', False)
            nanoseconds = int(val * Gst.SECOND)
            self.get_root().get_application().player.gst.seek_simple(
                Gst.Format.TIME,
                Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT,
                nanoseconds
            )
        GLib.timeout_add(500, lambda v=value: change_time(v) if v == scale_el.get_adjustment().get_value() else None)

    @Gtk.Template.Callback()
    def show_content_clicked(self, button):
        view = self.get_ancestor(Adw.NavigationSplitView)
        if view:
            view.set_show_content(True)

    @Gtk.Template.Callback()
    def change_rating(self, button):
        integration = get_current_integration()
        songId = integration.loaded_models.get('currentSong').get_property('songId')
        try:
            rating = int(button.get_name())
            if rating == integration.loaded_models.get(songId).get_property('userRating'):
                rating = 0
        except:
            return

        if integration.setRating(songId, rating):
            for i, el in enumerate(list(self.rating_container)):
                el.set_icon_name("starred-symbolic" if rating >= i+1 else "non-starred-symbolic")

    def change_bottom_sheet_state(self, playing:bool):
        bottom_sheet = self.get_ancestor(Adw.BottomSheet)
        if bottom_sheet:
            bottom_sheet.set_can_open(playing)
            if not playing:
                bottom_sheet.set_open(False)
            bottom_sheet.set_reveal_bottom_bar(playing)

        if root := self.get_root():
            if application := root.get_application():
                if playing:
                    application.inhibit_suspend()
                else:
                    application.uninhibit_suspend()
                    if popout_window := application.popout_window:
                        popout_window.close()

    def update_radioStreamUrl(self, radioStreamUrl:str):
        self.radio_homepage_el.set_visible(radioStreamUrl)
        self.positive_progress_el.set_visible(not radioStreamUrl)
        self.negative_progress_el.set_visible(not radioStreamUrl)
        self.progress_el.set_visible(not radioStreamUrl)
        self.rating_container.set_visible(self.rating_container.get_visible() and not radioStreamUrl)
        self.star_el.set_visible(self.star_el.get_visible() and not radioStreamUrl)

        homepage_url = ""
        if radioStreamUrl:
            stream_url = urlparse(radioStreamUrl)
            homepage_url = '{}://{}'.format(stream_url.scheme, stream_url.netloc)
        self.radio_homepage_el.set_tooltip_text(homepage_url)
        self.radio_homepage_el.set_action_target_value(GLib.Variant.new_string(homepage_url))

    def update_artistId(self, artistId:str):
        if artistId:
            self.artist_el.set_action_target_value(GLib.Variant.new_string(artistId))
            self.artist_el.set_action_name("app.show_artist")
            self.artist_el.set_sensitive(True)
        else:
            self.artist_el.set_action_name("")
            self.artist_el.set_sensitive(False)

    def update_album(self, album:str):
        self.album_el.get_child().set_label(album)
        self.album_el.set_tooltip_text(album)
        self.album_el.set_visible(album)

    def update_albumId(self, albumId:str):
        if albumId:
            self.album_el.set_action_target_value(GLib.Variant.new_string(albumId))
            self.album_el.set_action_name("app.show_album")
            self.album_el.set_sensitive(True)
        else:
            self.album_el.set_action_name("")
            self.album_el.set_sensitive(False)

    def update_isExternalFile(self, isExternalFile:bool):
        self.album_el.get_ancestor(Adw.WrapBox).set_sensitive(not isExternalFile)
        self.rating_container.set_visible(self.rating_container.get_visible() and not isExternalFile)
        self.star_el.set_visible(self.star_el.get_visible() and not isExternalFile)

    def update_userRating(self, userRating:int):
        for i, el in enumerate(list(self.rating_container)):
            el.set_icon_name("starred-symbolic" if userRating >= i+1 else "non-starred-symbolic")

    def update_starred(self, starred:bool):
        if starred:
            self.star_el.add_css_class('accent')
            self.star_el.remove_css_class('dim-label')
            self.star_el.set_icon_name('heart-filled-symbolic')
            self.star_el.set_tooltip_text(_('Favorite'))
        else:
            self.star_el.remove_css_class('accent')
            self.star_el.add_css_class('dim-label')
            self.star_el.set_icon_name('heart-outline-thick-symbolic')
            self.star_el.set_tooltip_text(_('Not Favorite'))

    def display_title_changed(self, display_title:str):
        self.title_el.set_label(display_title)
        self.title_el.set_tooltip_text(display_title)

    def display_artist_changed(self, display_artist:str):
        self.radio_homepage_el.set_visible(display_artist)
        self.artist_el.set_visible(display_artist)
        self.radio_homepage_el.get_child().set_label(display_artist)
        self.artist_el.get_child().set_label(display_artist)
        self.artist_el.set_tooltip_text(display_artist)

    def song_changed(self, song_id:str):
        def run():
            integration = get_current_integration()
            integration.verifySong(song_id, use_threading=False)
            if song_id in integration.loaded_models:
                # Set CoverArt
                paintable = integration.getCoverArt(song_id, big=True)
                if paintable:
                    GLib.idle_add(self.cover_el.remove_css_class, 'p50')
                else:
                    icon_theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
                    paintable = icon_theme.lookup_icon(
                        'music-note-symbolic',
                        None,
                        64,
                        1,
                        Gtk.TextDirection.NONE,
                        0
                    )
                    GLib.idle_add(self.cover_el.add_css_class, 'p50')
                GLib.idle_add(self.cover_el.set_paintable, paintable)

                # Set Defaults
                GLib.idle_add(self.rating_container.set_visible, True)
                GLib.idle_add(self.star_el.set_visible, True)
                GLib.idle_add(self.star_el.set_action_target_value, GLib.Variant.new_string(song_id))

                # Disconnect From Previous Song
                if previousSong := integration.loaded_models.get(self.song_connections.get('songId', '')):
                    for connection_id in self.song_connections.get('connections', []).copy():
                        try:
                            GLib.idle_add(previousSong.disconnect, connection_id)
                        except:
                            pass

                # Connect UI
                connections = {
                    'radioStreamUrl': self.update_radioStreamUrl,
                    'artistId': self.update_artistId,
                    'album': self.update_album,
                    'albumId': self.update_albumId,
                    'isExternalFile': self.update_isExternalFile,
                    'duration': self.progress_el.get_adjustment().set_upper,
                    'userRating': self.update_userRating,
                    'starred': self.update_starred
                }
                self.song_connections['connections'] = []
                self.song_connections['songId'] = song_id
                for property_name, cb in connections.items():
                    if connection_id := integration.connect_to_model(song_id, property_name, cb):
                        self.song_connections['connections'].append(connection_id)

        threading.Thread(target=run, daemon=True).start()

