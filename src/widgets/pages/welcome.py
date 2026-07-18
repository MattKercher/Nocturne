# welcome.py

from gi.repository import Gtk, Adw
from . import LoginDialog
from ...integrations import Local, Navidrome, NavidromeIntegrated, Bandcamp, Jellyfin, Offline
import threading

@Gtk.Template(resource_path='/com/jeffser/Nocturne/pages/welcome.ui')
class WelcomePage(Adw.NavigationPage):
    __gtype_name__ = 'NocturneWelcomePage'

    listbox_el = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        integrations = [Navidrome, NavidromeIntegrated, Jellyfin, Bandcamp, Local, Offline]
        for integration in integrations:
            metadata = integration.button_metadata
            row = Adw.ActionRow(
                title=metadata.get('title', _("Integration")),
                subtitle=metadata.get('subtitle', ""),
                tooltip_text=metadata.get('title', _("Integration")),
                activatable=True
            )
            if icon_name := integration.login_page_metadata.get('icon-name'):
                row.add_prefix(Gtk.Image(
                    icon_name=icon_name,
                    valign=Gtk.Align.CENTER
                ))
            row.add_suffix(Gtk.Image(
                icon_name="go-next-symbolic",
                valign=Gtk.Align.CENTER
            ))
            row.connect('activated', self.option_selected, integration)
            self.listbox_el.append(row)

    def option_selected(self, row, integration):
        integration = integration()
        if integration.check_if_ready(row):
            if integration.login_page_metadata.get('entries', []):
                dialog = LoginDialog(integration)
                dialog.present(self.get_root())
            else:
                threading.Thread(target=self.get_root().get_application().try_login, args=(integration,), daemon=True).start()


