# __init__.py

from .jellyfin import Jellyfin
from .navidrome import Navidrome, NavidromeIntegrated, Bandcamp
from .local import Local, Offline
from .base import Base
from . import models, secret
from ..constants import DATA_DIR
import os, requests
from gi.repository import Gio

integration = None

def get_all_subclasses(cls):
    subclasses = set()
    for s in cls.__subclasses__():
        subclasses.add(s)
        subclasses.update(get_all_subclasses(s))
    return subclasses

def get_available_integrations() -> dict:
    integrations = {}
    for cls in get_all_subclasses(Base):
        integrations[cls.__gtype_name__] = cls
    return integrations

def set_current_integration(new_integration):
    global integration
    integration = new_integration
    settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
    settings.set_string('selected-instance-type', integration.__gtype_name__)
    settings.set_string('integration-ip', integration.get_property('url'))
    settings.set_string('integration-user', integration.get_property('user'))
    if integration.__gtype_name__ != 'NocturneIntegrationOffline':
        settings.set_string("integration-library-dir", integration.get_property('libraryDir'))
    settings.set_boolean("integration-trust-server", integration.get_property('trustServer'))

