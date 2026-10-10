"""Keep connection passwords in the desktop keyring."""
import gi
gi.require_version('Secret', '1')
from gi.repository import Secret

SCHEMA = Secret.Schema.new('org.vncming.Connection', Secret.SchemaFlags.NONE,
                           {'id': Secret.SchemaAttributeType.STRING})


def lookup(identifier):
    if not identifier:
        return ''
    return Secret.password_lookup_sync(SCHEMA, {'id': identifier}, None) or ''


def store(identifier, label, password):
    if password:
        if not Secret.password_store_sync(SCHEMA, {'id': identifier}, Secret.COLLECTION_DEFAULT,
                                          'VNCMing · ' + label, password, None):
            raise RuntimeError('无法将密码保存到系统钥匙环。')
    else:
        clear(identifier)


def clear(identifier):
    if identifier:
        Secret.password_clear_sync(SCHEMA, {'id': identifier}, None)
