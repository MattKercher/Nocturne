# coverArt.py

from gi.repository import Gtk, Adw, Gdk, GLib, GObject, Gst, Gio
from ...integrations import get_current_integration
import threading

@Gtk.Template(resource_path='/com/jeffser/Nocturne/playing/cover_art.ui')
class PlayingCoverArt(Gtk.Box):
    __gtype_name__ = 'NocturnePlayingCoverArt'

    spectrum_el = Gtk.Template.Child()
    view_stack_el = Gtk.Template.Child()
    cover_el = Gtk.Template.Child()
    video_el = Gtk.Template.Child()
    view_switcher_el = Gtk.Template.Child()

    def setup(self):
        integration = get_current_integration()
        integration.connect_to_model('currentSong', 'songId', self.song_changed)
        integration.connect_to_model('currentSong', 'videoId', self.video_changed)
        self.spectrum_el.setup()

        if root := self.get_root():
            if app := root.get_application():
                if player := app.player:
                    if video_sink := player.gst.get_property('video-sink'):
                        self.video_el.set_paintable(video_sink.get_property('paintable'))

    def song_changed(self, songId:str):
        def run():
            integration = get_current_integration()
            if songId in integration.loaded_models:
                paintable = integration.getCoverArt(songId, big=True)
                if not paintable:
                    paintable = integration.getCoverArt(songId)

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
        threading.Thread(target=run, daemon=True).start()

    def video_changed(self, videoId:str):
        integration = get_current_integration()
        songId = integration.loaded_models.get('currentSong').get_property('songId')
        video_available = videoId and videoId == songId and self.video_el.get_paintable()
        self.view_switcher_el.set_visible(video_available)
        self.view_stack_el.set_visible_child_name('video' if video_available else 'audio')

