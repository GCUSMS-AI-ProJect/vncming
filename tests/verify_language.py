"""Check locale defaults and persisted selection without real connections or keyring access."""
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'app'))
import i18n
import viewer
import file_transfer
from gi.repository import Gtk, GLib

assert i18n.system_language({'LANG': 'zh_CN.UTF-8'}) == 'zh_CN'
assert i18n.system_language({'LANG': 'en_US.UTF-8'}) == 'en'
assert i18n.system_language({'LANG': 'fr_FR.UTF-8'}) == 'en'
assert i18n.system_language({'LANG': 'en_US.UTF-8', 'LC_MESSAGES': 'zh_CN.UTF-8'}) == 'zh_CN'
assert i18n.system_language({'LANG': 'zh_CN.UTF-8', 'LC_ALL': 'C', 'LANGUAGE': 'zh_CN'}) == 'en'
assert i18n.system_language({'LANG': 'zh_CN.UTF-8', 'LANGUAGE': 'en:zh_CN'}) == 'en'
assert i18n.system_language({'LANG': 'en_US.UTF-8', 'LANGUAGE': 'zh_CN:en'}) == 'zh_CN'

def close(window):
    window.disconnect_by_func(Gtk.main_quit)
    window.destroy()

with tempfile.TemporaryDirectory(prefix='vncming-language-') as temporary:
    viewer.DATA = Path(temporary) / 'connections.json'
    viewer.LEGACY_DATA = Path(temporary) / 'legacy.json'
    entry = dict(name='连接', address='192.0.2.20', username='用户')
    viewer.DATA.write_text(json.dumps({'connections': [entry], 'options': {'Maximize': True}}))
    with patch.dict(os.environ, {'LC_ALL': 'zh_CN.UTF-8', 'LANGUAGE': ''}):
        first = viewer.Viewer(show_window=False)
        assert first.language_preference == 'system'
        assert first.connect_button.get_label() == '连接'
        assert first.menu_bar.get_children()[2].get_label() == '语言'
        messages = []
        first.message = messages.append
        original_save = first.save
        first.save = lambda: False
        first.language_items['en'].set_active(True)
        assert first.language_preference == 'system'
        assert first.language_items['system'].get_active() and not messages
        first.save = original_save
        first.language_items['en'].set_active(True)
        assert not messages, "Live switching must not display a restart dialog"
        saved = json.loads(viewer.DATA.read_text())
        assert saved['language'] == 'en' and saved['connections'] == [entry]
        assert first.connect_button.get_label() == 'Connect', 'Switching must apply immediately'
        assert first.menu_bar.get_children()[2].get_label() == 'Language'
        close(first)
        second = viewer.Viewer(show_window=False)
        assert second.language_preference == 'en'
        assert second.connect_button.get_label() == 'Connect'
        assert second.menu_bar.get_children()[2].get_label() == 'Language'
        assert second.entries == [entry], 'User names and connection data must never be translated'
        original_environment = dict(os.environ)
        environment = i18n.native_environment(original_environment, viewer.ROOT / 'build/locale')
        assert environment['LANGUAGE'] == 'en'
        assert environment['VNCMING_LANGUAGE'] == 'en'
        assert original_environment == dict(os.environ)
        second.message = lambda *_: None
        second.language_items['zh_CN'].set_active(True)
        close(second)
    with patch.dict(os.environ, {'LC_ALL': 'en_US.UTF-8', 'LANGUAGE': ''}):
        third = viewer.Viewer(show_window=False)
        assert third.connect_button.get_label() == '连接', 'Explicit Chinese must override English system locale'
        third.message = lambda *_: None
        third.language_items['system'].set_active(True)
        close(third)
        fourth = viewer.Viewer(show_window=False)
        assert fourth.connect_button.get_label() == 'Connect', 'System default must resume following the locale'
        transfer = file_transfer.TransferWindow(fourth, entry)
        fourth.transfer_windows['fixture'] = transfer
        try:
            assert transfer.login_button.get_label() == 'Connect'
            assert transfer.get_titlebar().get_title() == 'File Transfer · 连接'
            assert transfer.connection_actions['重新连接…'].get_property('text') == 'Reconnect…'
            assert transfer.other.view.get_column(0).get_title() == 'Name'
            assert transfer.local.path_buttons[0].get_tooltip_text() == 'Parent Directory'
            task = dict(upload=True, status='等待中', path='/fixture', destination='/fixture2', done=0, total=0)
            import threading
            task['cancel'] = threading.Event()
            task['iter'] = transfer.task_model.append(['fixture', 'Upload', '', 0, '', '', task, ''])
            transfer.tasks.append(task)
            transfer.update_task(task, 0, 0, '等待中', '')
            assert transfer.task_model[task['iter']][2] == 'Waiting'
            task.update(status='已完成', skipped=2)
            transfer.update_task(task, 0, 0, '已完成', '')
            assert transfer.task_model[task['iter']][2] == 'Completed · 2 skipped'
            assert transfer.task_model[task['iter']][3] == 100
            assert task['status'] == '已完成', 'Internal task state must stay independent of language'
            fourth.table.select_row(fourth.table.get_row_at_index(0))
            fourth.address.set_text('192.0.2.99::5999')
            original_widgets = (fourth.address, fourth.table, fourth.connect_button, transfer.local.view, transfer.task_model)
            original_selection = fourth.table.get_selected_row()
            task['status'] = '正在传输'
            transfer.update_task(task, 250, 1000, '正在传输', '20 KB/s')
            original_progress = tuple(transfer.task_model[task['iter']][index] for index in (3, 4, 5))
            fourth.language_items['zh_CN'].set_active(True)
            assert fourth.connect_button.get_label() == '连接'
            assert fourth.address.get_text() == '192.0.2.99::5999'
            assert fourth.table.get_selected_row() is original_selection
            assert fourth.entries == [entry]
            assert transfer.login_button.get_label() == '连接'
            assert transfer.get_titlebar().get_title() == '文件传输 · 连接'
            assert transfer.get_title() == '文件传输 · 连接', (transfer.get_title(), i18n._bindings.get(transfer))
            assert transfer.connection_actions['重新连接…'].get_property('text') == '重新连接…'
            assert transfer.task_model[task['iter']][2] == '正在传输'
            assert tuple(transfer.task_model[task['iter']][index] for index in (3, 4, 5)) == original_progress
            assert task['status'] == '正在传输' and not task['cancel'].is_set()
            fourth.language_items['en'].set_active(True)
            assert transfer.task_model[task['iter']][2] == 'Transferring'
            assert transfer.get_title() == 'File Transfer · 连接'
            assert transfer.other.view.get_column(0).get_title() == 'Name'
            assert original_widgets == (fourth.address, fourth.table, fourth.connect_button, transfer.local.view, transfer.task_model)
            def walk(widget):
                yield widget
                if isinstance(widget, Gtk.Container):
                    for child in widget.get_children():
                        yield from walk(child)
            dialog_checks = []
            def switch_open_dialog():
                dialog = next(w for w in Gtk.Window.list_toplevels()
                              if isinstance(w, Gtk.Dialog) and w.get_visible())
                combos = [w for w in walk(dialog) if isinstance(w, Gtk.ComboBoxText)]
                selected = [combo.get_active_id() for combo in combos]
                fourth.language_items['zh_CN'].set_active(True)
                assert dialog.get_title() == '连接选项'
                assert dialog.get_widget_for_response(Gtk.ResponseType.OK).get_label() == '确定'
                assert [combo.get_active_id() for combo in combos] == selected
                assert any(combo.get_model()[0][0] == '普通窗口' for combo in combos)
                dialog_checks.append(True)
                dialog.response(Gtk.ResponseType.CANCEL)
                return False
            GLib.timeout_add(50, switch_open_dialog)
            fourth.show_options()
            assert dialog_checks
            task['status'] = '已完成'
            transfer.update_task(task, 1000, 1000, '已完成', '')
        finally:
            transfer.destroy()
            transfer.worker_thread.join(5)
            close(fourth)
    invalid = json.loads(viewer.DATA.read_text())
    invalid['language'] = 'unsupported'
    viewer.DATA.write_text(json.dumps(invalid))
    with patch.dict(os.environ, {'LC_ALL': 'zh_CN.UTF-8', 'LANGUAGE': ''}):
        fallback = viewer.Viewer(show_window=False)
        assert fallback.language_preference == 'system' and fallback.connect_button.get_label() == '连接'
        close(fallback)
print('System locale, saved overrides, live switching without widget replacement, user data preservation and translated transfer states passed')
