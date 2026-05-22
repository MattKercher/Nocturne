# popout_window.py

from gi.repository import Gtk, Adw, GLib, Gst, Gio, GObject, Pango, Gdk
from . import PlayingControlPage
from ...integrations import get_current_integration
from ...constants import get_display_time
import threading

@Gtk.Template(resource_path='/com/jeffser/Nocturne/playing/popout_window.ui')
class PopoutWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'NocturnePopoutWindow'

    toolbarview = Gtk.Template.Child()
    header_view_switcher = Gtk.Template.Child()
    breakpoint_el = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    playing_page = Gtk.Template.Child()
    lyrics_page = Gtk.Template.Child()
    queue_page = Gtk.Template.Child()
    footer = Gtk.Template.Child()
    split_view = Gtk.Template.Child()
    footer_spectrum_el = Gtk.Template.Child()

    bottom_bar = Gtk.Template.Child()
    fs_spectrum_el = Gtk.Template.Child()
    fs_title_el = Gtk.Template.Child()
    fs_progress_el = Gtk.Template.Child()
    fs_album_el = Gtk.Template.Child()
    fs_artist_el = Gtk.Template.Child()
    fs_timestamp_el = Gtk.Template.Child()
    state_stack_el = Gtk.Template.Child()
    cover_el = Gtk.Template.Child()
    sidebar_stack = Gtk.Template.Child()
    toggle_fullscreen_el = Gtk.Template.Child()

    song_connections = {
        'songId': '',
        'connections': []
    }

    def __init__(self, application, fullscreened):
        super().__init__(
            application=application,
            fullscreened=fullscreened
        )

        integration = get_current_integration()
        current_song_id = integration.loaded_models.get('currentSong').get_property('songId')
        self.playing_page.last_song_id = current_song_id

        GLib.idle_add(self.playing_page.setup)
        GLib.idle_add(self.lyrics_page.setup)
        GLib.idle_add(self.footer.setup)
        GLib.idle_add(self.queue_page.setup)

        self.playing_page.header_bar.get_ancestor(Adw.ToolbarView).set_extend_content_to_top_edge(False)
        self.playing_page.header_bar.set_show_start_title_buttons(True)
        self.playing_page.header_bar.set_show_end_title_buttons(True)

        self.footer.set_property('forceHugeMode', True)
        integration.connect_to_model('currentSong', 'songId', self.song_changed)
        integration.connect_to_model('currentSong', 'positionSeconds', self.song_position_changed)
        integration.connect_to_model('currentSong', 'buttonState', self.state_stack_el.set_visible_child_name)
        integration.connect_to_model('currentSong', 'displaySongTitle', self.display_title_changed)
        integration.connect_to_model('currentSong', 'displaySongArtist', self.display_artist_changed)

        fullscreen_btn = Gtk.Button(
            icon_name="view-fullscreen-symbolic",
            tooltip_text=_("Toggle Fullscreen")
        )
        fullscreen_btn.connect('clicked', self.toggle_fullscreen)
        self.playing_page.header_bar.pack_start(fullscreen_btn)
        self.footer_spectrum_el.setup()
        self.fs_spectrum_el.setup()

        self.settings = Gio.Settings(schema_id="com.jeffser.Nocturne")

        self.settings.connect('changed::popout-dynamic-bg-mode', self.dynamic_bg_mode_changed)
        self.dynamic_bg_mode_changed(self.settings, 'popout-dynamic-bg-mode')
        self.settings.connect('changed::use-dynamic-accent', self.css_toggled, 'dynamic-accent')
        self.css_toggled(self.settings, 'use-dynamic-accent', 'dynamic-accent')

    def css_toggled(self, settings, key, css_class):
        if settings.get_value(key).unpack():
            self.add_css_class(css_class)
        else:
            self.remove_css_class(css_class)

    def dynamic_bg_mode_changed(self, settings, key):
        value = settings.get_value(key).unpack()
        self.remove_css_class('dynamic-bg-gradient')
        self.remove_css_class('dynamic-bg-blur')
        if value:
            self.add_css_class('dynamic-bg-{}'.format(value))

    def song_position_changed(self, positionSeconds:int):
        integration = get_current_integration()
        songId = integration.loaded_models.get('currentSong').get_property('songId')
        if model := integration.loaded_models.get(songId):
            duration = model.get_property('duration')
            self.fs_timestamp_el.set_label('-{}'.format(get_display_time(duration - positionSeconds)))
        self.fs_progress_el.set_value(positionSeconds)

    @Gtk.Template.Callback()
    def close_request(self, window):
        if application := self.get_application():
            application.uninhibit_idle()
        if self.get_application().main_window.get_hide_on_close():
            self.get_application().main_window.present()

    @Gtk.Template.Callback()
    def toggle_fullscreen(self, button):
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            self.fullscreen()

    def update_radioStreamUrl(self, radioStreamUrl:str):
        isRadio = bool(radioStreamUrl)
        self.fs_artist_el.set_visible(not isRadio)
        self.fs_album_el.set_visible(not isRadio)
        self.fs_timestamp_el.set_visible(not isRadio)
        self.fs_progress_el.set_visible(not isRadio)

    def update_artistId(self, artistId:list):
        if artistId:
            self.fs_artist_el.set_action_target_value(GLib.Variant.new_string(artistId))
            self.fs_artist_el.set_action_name("app.show_artist")
            self.fs_artist_el.set_sensitive(True)
        else:
            self.fs_artist_el.set_action_name("")
            self.fs_artist_el.set_sensitive(False)

    def update_album(self, album:str):
        self.fs_album_el.get_child().set_label(album)
        self.fs_album_el.set_tooltip_text(album)
        self.fs_album_el.set_visible(album)

    def update_albumId(self, albumId:str):
        if albumId:
            self.fs_album_el.set_action_target_value(GLib.Variant.new_string(albumId))
            self.fs_album_el.set_action_name("app.show_album")
            self.fs_album_el.set_sensitive(True)
        else:
            self.fs_album_el.set_action_name("")
            self.fs_album_el.set_sensitive(False)

    def display_title_changed(self, display_title:str):
        self.fs_title_el.set_label(display_title)
        self.set_title(display_title or "Nocturne")

    def display_artist_changed(self, display_artist:str):
        self.fs_artist_el.get_child().set_label(display_artist)
        self.fs_artist_el.set_tooltip_text(display_artist)
        self.fs_artist_el.set_visible(display_artist)

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
                    'duration': self.fs_progress_el.get_adjustment().set_upper
                }
                self.song_connections['connections'] = []
                self.song_connections['songId'] = song_id
                for property_name, cb in connections.items():
                    if connection_id := integration.connect_to_model(song_id, property_name, cb):
                        self.song_connections['connections'].append(connection_id)

        threading.Thread(target=run, daemon=True).start()

    @Gtk.Template.Callback()
    def progress_bar_changed(self, scale_el, scroll_type, value):
        self.playing_page.progress_bar_changed(scale_el, scroll_type, value)

    @Gtk.Template.Callback()
    def big_mode_apply(self, breakpoint_el):
        self.add_css_class('big-mode')

    @Gtk.Template.Callback()
    def big_mode_unapply(self, breakpoint_el):
        self.remove_css_class('big-mode')

    @Gtk.Template.Callback()
    def fullscreen_toggled(self, window, gparam):
        fullscreen = window.is_fullscreen()
        self.toggle_fullscreen_el.set_icon_name('view-unfullscreen-symbolic' if fullscreen else 'view-fullscreen-symbolic')
        if application := self.get_application():
            if fullscreen:
                application.inhibit_idle(self)
            else:
                application.uninhibit_idle()
