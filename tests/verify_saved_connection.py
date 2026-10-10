import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
"""Exercise row actions, edited fields, keyring storage and pipe authentication."""
import json
import socket
import struct
import tempfile
import threading
import time
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
import viewer
import credentials

result = {}
with tempfile.TemporaryDirectory(prefix='vncming-check-') as temporary:
    viewer.DATA = Path(temporary) / 'connections.json'
    viewer.LEGACY_DATA = Path(temporary) / 'legacy.json'
    window = viewer.Viewer()
    window.entries = [{'name': 'UI Test', 'address': '127.0.0.1'}]
    window.refresh()
    original_dialog = window.connection_dialog
    opened = []
    window.connection_dialog = lambda i=None: opened.append(i)
    window.table.emit('row-activated', window.table.get_row_at_index(0))
    assert opened == [0]
    window.connection_dialog = original_dialog
    dispatched = []
    original_connect = window.connect_entry
    window.connect_entry = lambda i: dispatched.append(i)
    row = window.table.get_row_at_index(0)
    row.get_child().get_children()[-1].get_children()[0].clicked()
    assert dispatched == [0]
    window.connect_entry = original_connect
    window.entries.append({'name': 'Delete Test', 'address': '127.0.0.2'})
    window.refresh()
    window.table.select_row(window.table.get_row_at_index(0))
    window.table.get_row_at_index(1).get_child().get_children()[-1].get_children()[1].clicked()
    assert [entry['name'] for entry in window.entries] == ['UI Test']
    assert json.loads(viewer.DATA.read_text())['connections'] == window.entries
    result['row_actions'] = True

    original_popen = viewer.subprocess.Popen
    def waiting_engine(args, **kwargs):
        return original_popen(['/bin/sleep', '30'], **kwargs)
    viewer.subprocess.Popen = waiting_engine
    original_message = window.message
    messages = []
    window.message = messages.append
    try:
        window.start_connection('127.0.0.1::5999')
        pending = window.pending_connections['127.0.0.1::5999']
        window.start_connection('127.0.0.1::5999')
        assert len(window.children) == 1
        pending['started'] -= 11000000
        assert window.poll_pending('127.0.0.1::5999') is False
        pending['process'].wait(3)
        assert messages and '连接超时' in messages[0]
        assert not window.pending_connections
        window.poll_child(pending['process'], '127.0.0.1::5999')
        result['timeout_and_duplicate_protection'] = True
    finally:
        viewer.subprocess.Popen = original_popen
        window.message = original_message

    def entries(widget):
        found = [widget] if isinstance(widget, Gtk.Entry) else []
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                found.extend(entries(child))
        return found

    def fill():
        for dialog in Gtk.Window.list_toplevels():
            if isinstance(dialog, Gtk.Dialog) and dialog.get_title() == '连接属性':
                fields = entries(dialog.get_content_area())
                # GtkGrid child order is not its visible row order.
                fields.sort(key=lambda field: field.get_parent().child_get_property(field, 'top-attach'))
                assert len(fields) == 4
                for field, value in zip(fields, ['Saved Test', '127.0.0.1', 'test-user', 'test-password']):
                    field.set_text(value)
                assert not fields[3].get_visibility()
                dialog.response(Gtk.ResponseType.OK)
        return False

    GLib.timeout_add(300, fill)
    window.connection_dialog(0)
    saved = window.entries[0]
    try:
        assert saved['username'] == 'test-user'
        assert credentials.lookup(saved['credential_id']) == 'test-password'
        assert 'test-password' not in viewer.DATA.read_text()
        result['edited_credentials_and_keyring'] = True
        window.save_connection('New Test', '127.0.0.2', 'user-a', '')
        assert window.entries[0]['name'] == 'New Test'
        identifier = window.entries[0]['credential_id']
        window.save_connection('Updated Test', '127.0.0.2', 'user-a', '')
        assert len(window.entries) == 2
        assert window.entries[0]['credential_id'] == identifier
        window.save_connection('Other User', '127.0.0.2', 'user-b', '')
        assert len(window.entries) == 3
        window.save_connection('Merged Test', '127.0.0.2', 'user-a', '', index=0)
        assert len(window.entries) == 2
        assert window.entries[0]['credential_id'] == identifier
        window.save_connection('Saved Test', '127.0.0.1', 'test-user', 'test-password')
        saved = window.entries[0]
        assert json.loads(viewer.DATA.read_text())['connections'][0] == saved
        row = window.table.get_row_at_index(0)
        marker = row.get_child().get_children()[0].get_children()[-1]
        assert marker.get_label() == '★'
        result['newest_first_and_username_address_deduplication'] = True
        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        complete = threading.Event()
        release = threading.Event()
        errors = []
        def serve():
            try:
                connection, _ = server.accept()
                connection.settimeout(8)
                def read(count):
                    data = b''
                    while len(data) < count:
                        part = connection.recv(count-len(data))
                        if not part:
                            raise EOFError()
                        data += part
                    return data
                with connection:
                    connection.sendall(b'RFB 003.008\n'); read(12)
                    connection.sendall(b'\x01\x13'); assert read(1) == b'\x13'
                    connection.sendall(b'\x00\x02'); assert read(2) == b'\x00\x02'
                    connection.sendall(b'\x00\x01'+struct.pack('!I',256))
                    assert read(4) == struct.pack('!I',256)
                    connection.sendall(b'\x00\x00\x00\x00')
                    u, p = struct.unpack('!II', read(8))
                    assert read(u) == b'test-user' and read(p) == b'test-password'
                    result['automatic_pipe_authentication'] = True
                    complete.set()
                    release.wait(10)
            except Exception as error:
                errors.append(type(error).__name__)
                complete.set()
            finally:
                server.close()
        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        window.options['Shared'] = True
        saved['address'] = '127.0.0.1::' + str(server.getsockname()[1])
        original_popen = viewer.subprocess.Popen
        def fixture_engine(args, **kwargs):
            # The local fixture advertises unencrypted Plain auth only.
            return original_popen(args[:-1] + ['-SecurityTypes=Plain'] + args[-1:], **kwargs)
        viewer.subprocess.Popen = fixture_engine
        window.connect_entry(0)
        viewer.subprocess.Popen = original_popen
        assert complete.wait(10), 'Authentication timed out'
        assert not errors, errors
        assert window.poll_pending(saved['address']) is False
        assert saved['address'] not in window.pending_connections
        result['connection_progress_completed'] = True
        for process in window.children.values():
            process.terminate()
            process.wait(5)
        release.set()
        worker.join(3)
    finally:
        credentials.clear(saved.get('credential_id'))
        window.destroy()
        while Gtk.events_pending():
            Gtk.main_iteration()
print(json.dumps(result))
