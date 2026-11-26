# download_row.py

from gi.repository import Gtk, GObject

@Gtk.Template(resource_path='/com/jeffser/Nocturne/containers/download_row.ui')
class DownloadRow(Gtk.ListBoxRow):
    __gtype_name__ = 'NocturneDownloadRow'

    title_label = Gtk.Template.Child()
    done_label = Gtk.Template.Child()
    progressbar = Gtk.Template.Child()
    done_button = Gtk.Template.Child()

    def __init__(self, model):
        self.model = model
        integration = Gtk.Application.get_default().get_property('integration')
        integration.verifySong(self.model.get_property('songId'))
        super().__init__()
        title = integration.loaded_models.get(self.model.get_property('songId')).get_property('title')
        self.title_label.set_label(title)
        self.set_tooltip_text(title)
        self.model.bind_property(
            "progress",
            self.progressbar,
            "fraction",
            GObject.BindingFlags.DEFAULT | GObject.BindingFlags.SYNC_CREATE
        )

    @Gtk.Template.Callback()
    def progressbar_frac_changed(self, progressbar, ud):
        if progressbar.get_fraction() == 1:
            self.done_button.set_visible(True)
            self.done_label.set_visible(True)
            progressbar.set_visible(False)

    @Gtk.Template.Callback()
    def remove_from_queue(self, button):
        player = Gtk.Application.get_default().get_property('player')
        download_queue = player.get_property('downloadQueueModel')
        found, position = download_queue.find_with_equal_func(
            self.model,
            lambda item_a, item_b, ud: item_a.get_property('songId') == item_b.get_property('songId'),
            0
        )
        if found and position >= 0:
            download_queue.remove(position)

