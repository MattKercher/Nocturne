# songs_starred.py

from gi.repository import Gtk, Adw, GLib
from ...integrations import get_current_integration
from ..song import SongRow, SongButton
import re, threading

@Gtk.Template(resource_path='/com/jeffser/Nocturne/pages/songs_starred.ui')
class SongsStarredPage(Adw.NavigationPage):
    __gtype_name__ = 'NocturneSongsStarredPage'

    list_el = Gtk.Template.Child()
    wrapbox_el = Gtk.Template.Child()
    search_entry_el = Gtk.Template.Child()
    main_stack = Gtk.Template.Child()
    scrolledwindow = Gtk.Template.Child()
    song_ids = []
    offset = 0
    searching = False

    def __init__(self):
        super().__init__()
        self.scrolledwindow.get_vadjustment().connect('notify::upper', lambda va, ud: GLib.timeout_add(1000, self.check_scrollbar, va))

    def search(self):
        if self.searching:
            return
        self.searching = True
        integration = get_current_integration()
        ids_to_show = []
        if query := self.search_entry_el.get_text():
            for song_id in self.song_ids:
                if model := integration.loaded_models.get(song_id):
                    if re.search(query, model.get_property('title') + model.get_property('artist'), re.IGNORECASE):
                        ids_to_show.append(song_id)
        else:
            ids_to_show = self.song_ids

        ids_to_show = ids_to_show[:self.offset+30]
        missing_ids = ids_to_show.copy()

        for widget in list(self.list_el.list_el) + list(self.wrapbox_el):
            GLib.idle_add(widget.set_visible, widget.id in ids_to_show)
            if widget.id in missing_ids:
                missing_ids.remove(widget.id)

        for song_id in missing_ids:
            GLib.idle_add(self.list_el.list_el.append, SongRow(song_id))
            GLib.idle_add(self.wrapbox_el.append, SongButton(song_id))
        self.offset += 30
        GLib.idle_add(self.update_visibility)
        self.searching = False

    def check_scrollbar(self, adjustment):
        if adjustment.get_upper() <= adjustment.get_page_size():
            threading.Thread(target=self.search).start()

    def reset(self):
        self.offset = 0
        self.list_el.list_el.remove_all()
        for el in list(self.wrapbox_el):
            self.wrapbox_el.remove(el)
        integration = get_current_integration()
        self.song_ids = integration.getStarredSongs()

    def reload(self):
        GLib.idle_add(self.main_stack.set_visible_child_name, 'loading')
        GLib.idle_add(self.reset)
        GLib.idle_add(self.search)

    @Gtk.Template.Callback()
    def on_search(self, search_entry):
        self.offset = 0
        threading.Thread(target=self.search, daemon=True).start()

    @Gtk.Template.Callback()
    def scroll_edge_reached(self, scrolledwindow, pos):
        if pos == Gtk.PositionType.BOTTOM and self.offset < len(self.song_ids):
            threading.Thread(target=self.search, daemon=True).start()

    def update_visibility(self):
        for row in list(self.list_el.list_el):
            if row.get_visible():
                self.main_stack.set_visible_child_name('content')
                self.list_el.main_stack.set_visible_child_name('content')
                return
        self.main_stack.set_visible_child_name('no-content')
        self.list_el.main_stack.set_visible_child_name('no-content')
