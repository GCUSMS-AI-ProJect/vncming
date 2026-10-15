import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
"""Exercise row actions, edited fields, keyring storage and pipe authentication."""
import json
import select
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
    viewer.DATA.write_text(json.dumps({'options': {'FullScreen': True}, 'connections': []}))
    window = viewer.Viewer()
    assert window.options['FullScreen'] is False and window.options['Maximize'] is True
    result['legacy_fullscreen_migrated_to_maximized'] = True
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
    def delete_response(response):
        def respond():
            for dialog in Gtk.Window.list_toplevels():
                if isinstance(dialog, Gtk.Dialog) and dialog.get_title() == '删除连接？' and dialog.get_visible():
                    dialog.response(response)
            return False
        GLib.timeout_add(100, respond)
    delete_response(Gtk.ResponseType.CANCEL)
    window.table.get_row_at_index(1).get_child().get_children()[-1].get_children()[1].clicked()
    assert len(window.entries) == 2, 'Cancelling deletion must preserve the device'
    delete_response(Gtk.ResponseType.OK)
    window.table.get_row_at_index(1).get_child().get_children()[-1].get_children()[1].clicked()
    assert [entry['name'] for entry in window.entries] == ['UI Test']
    assert json.loads(viewer.DATA.read_text())['connections'] == window.entries
    result['row_actions'] = True
    result['delete_confirmation'] = True

    def walk(widget):
        yield widget
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                yield from walk(child)
    original_options = window.options.copy()
    for opening, resolution in [('fullscreen', 'dynamic'), ('normal', 'server'), ('maximized', 'fixed')]:
        def set_options():
            for dialog in Gtk.Window.list_toplevels():
                if isinstance(dialog, Gtk.Dialog) and dialog.get_title() == '连接选项' and dialog.get_visible():
                    combos = [w for w in walk(dialog) if isinstance(w, Gtk.ComboBoxText)]
                    combos.sort(key=lambda field: field.get_parent().child_get_property(field, 'top-attach'))
                    assert len(combos) == 2
                    combos[0].set_active_id(opening)
                    combos[1].set_active_id(resolution)
                    dialog.response(Gtk.ResponseType.OK)
            return False
        GLib.timeout_add(100, set_options)
        window.show_options()
        assert window.options['FullScreen'] == (opening == 'fullscreen')
        assert window.options['Maximize'] == (opening == 'maximized')
        assert window.options['FixedResolution'] == (resolution == 'fixed')
        assert window.options['RemoteResize'] == (resolution == 'dynamic')
    window.options = original_options
    window.save()
    result['exclusive_window_and_resolution_modes'] = True

    original_popen = viewer.subprocess.Popen
    def waiting_engine(args, **kwargs):
        assert '-FullScreen=0' in args and '-Maximize=1' in args, args
        assert '-DesktopSize=1920x1080' in args and not any(arg.startswith('-FixedResolution') for arg in args), args
        return original_popen(['/bin/sleep', '30'], **kwargs)
    viewer.subprocess.Popen = waiting_engine
    original_message = window.message
    messages = []
    window.message = messages.append
    try:
        window.start_connection('127.0.0.1::5999')
        pending = window.pending_connections['127.0.0.1::5999']
        window.address.set_text('127.0.0.1::5999')
        assert not window.connect_button.get_sensitive()
        window.start_connection('127.0.0.1::5999')
        assert len(window.children) == 1
        pending['started'] -= 11000000
        assert window.poll_pending('127.0.0.1::5999') is False
        pending['process'].wait(3)
        assert len(messages) == 1 and '连接超时' in messages[0]
        assert not window.pending_connections
        assert window.connect_button.get_sensitive()
        assert not pending['dialog'].get_visible()
        assert window.poll_pending('127.0.0.1::5999') is False
        assert len(messages) == 1
        window.poll_child(pending['process'], '127.0.0.1::5999')
        result['timeout_and_duplicate_protection'] = True
    finally:
        viewer.subprocess.Popen = original_popen
        window.message = original_message

    # Fullscreen dynamic sizing must override the engine's historical fixed
    # fullscreen default, so the selected mode reaches the native process.
    captured = []
    def capture_launch(args, **kwargs):
        captured.append(args)
        return original_popen(['/bin/sleep', '30'], **kwargs)
    viewer.subprocess.Popen = capture_launch
    try:
        window.options.update(FullScreen=True, Maximize=False, FixedResolution=False, RemoteResize=True)
        window.start_connection('127.0.0.1::5998')
        process = window.pending_connections['127.0.0.1::5998']['process']
        assert '-FullScreenDesktopSize=' in captured[-1]
        assert '-RemoteResize=1' in captured[-1]
        assert '-FullScreen=1' in captured[-1] and '-Maximize=0' in captured[-1]
        assert '-DesktopSize=1920x1080' not in captured[-1]
        window.cancel_pending('127.0.0.1::5998')
        process.wait(3)
        window.poll_child(process, '127.0.0.1::5998')
        result['dynamic_fullscreen_launch_parameters'] = True
    finally:
        window.options = original_options
        viewer.subprocess.Popen = original_popen

    # A real native connection error must stop the launcher timeout even while
    # its own error dialog remains open beyond the ten-second deadline.
    with socket.socket() as refused:
        refused.bind(('127.0.0.1', 0))  # Bound but not listening.
        address = '127.0.0.1::' + str(refused.getsockname()[1])
        messages = []
        window.message = messages.append
        process = None
        try:
            window.start_connection(address)
            pending = window.pending_connections[address]
            process = pending['process']
            assert select.select([pending['descriptor']], [], [], 5)[0]
            pending['started'] -= 11000000
            assert window.poll_pending(address) is False
            assert address not in window.pending_connections
            assert not pending['dialog'].get_visible()
            assert window.poll_pending(address) is False
            assert not messages, messages
            assert process.poll() is None, 'Native error dialog should remain open'
            result['native_error_has_no_duplicate_timeout'] = True
        finally:
            window.message = original_message
            if process is not None:
                process.terminate()
                process.wait(5)
                window.poll_child(process, address)

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
        assert marker.get_label() == '最近保存'
        result['newest_first_and_username_address_deduplication'] = True
        incoming, outgoing = socket.socketpair(type=socket.SOCK_DGRAM)
        incoming.setblocking(False)
        user, secret = b'updated-user', b'updated-password'
        outgoing.send(struct.pack('!II', len(user), len(secret)) + user + secret)
        saved['ssh_port'] = 2222
        assert window.poll_saved_credentials(None, incoming, saved['address'], saved['credential_id']) is False
        outgoing.close()
        updated = window.entries[0]
        assert updated['name'] == 'Saved Test' and updated['username'] == 'updated-user'
        assert updated['credential_id'] == saved['credential_id'] and updated['ssh_port'] == 2222
        assert credentials.lookup(updated['credential_id']) == 'updated-password'
        assert 'updated-password' not in viewer.DATA.read_text()
        # Saving must not restore a device deleted while login was open.
        incoming, outgoing = socket.socketpair(type=socket.SOCK_DGRAM)
        outgoing.send(struct.pack('!II', len(user), len(secret)) + user + secret)
        before = window.entries.copy()
        window.poll_saved_credentials(None, incoming, saved['address'], 'deleted-device')
        outgoing.close()
        assert window.entries == before
        result['authentication_feedback_saved_to_keyring'] = True
        window.save_connection('Saved Test', '127.0.0.1', 'test-user', 'test-password', index=0)
        saved = window.entries[0]
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
