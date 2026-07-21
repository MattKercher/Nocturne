# wrapbox.py

from gi.repository import GObject, Gtk, GLib

@Gtk.Template(resource_path='/com/jeffser/Nocturne/containers/wrapbox.ui')
class Wrapbox(Gtk.Box):
    __gtype_name__ = 'NocturneWrapbox'

    header_button = Gtk.Template.Child()
    list_el = Gtk.Template.Child()
    header_label = GObject.Property(type=str, default="")
    header_icon_name = GObject.Property(type=str, default="")
    header_page_tag = GObject.Property(type=str, default="")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind_property(
            "header-label",
            self.header_button,
            "tooltip-text",
            GObject.BindingFlags.SYNC_CREATE,
            lambda bind, value: value or "",
            None
        )
        self.bind_property(
            "header-label",
            self.header_button,
            "visible",
            GObject.BindingFlags.SYNC_CREATE,
            lambda bind, value: bool(value),
            None
        )
        self.bind_property(
            "header-label",
            self.header_button.get_child(),
            "label",
            GObject.BindingFlags.SYNC_CREATE,
            lambda bind, value: value or "",
            None
        )
        self.bind_property(
            "header-icon-name",
            self.header_button.get_child(),
            "icon-name",
            GObject.BindingFlags.SYNC_CREATE,
            lambda bind, value: value or "view-list-bullet-symbolic",
            None
        )
        self.bind_property(
            "header-page-tag",
            self.header_button,
            "action-name",
            GObject.BindingFlags.SYNC_CREATE,
            lambda bind, value: "app.replace_root_page" if value else "",
            None
        )
        self.bind_property(
            "header-page-tag",
            self.header_button,
            "action-target",
            GObject.BindingFlags.SYNC_CREATE,
            lambda bind, value: GLib.Variant.new_string(value or ""),
            None
        )

    def remove_all(self):
        for child in list(self.list_el):
            self.list_el.remove(child)

    def set_widgets(self, widgets:list):
        if len(list(self.list_el)):
            GLib.idle_add(self.remove_all)
        GLib.idle_add(self.set_visible, len(widgets) > 0)
        for page in widgets:
            GLib.idle_add(self.list_el.append, page)
