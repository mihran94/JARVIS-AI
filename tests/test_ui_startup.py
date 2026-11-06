"""Real Qt widget regression checks, without audio backend or provider calls."""
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HAVE_QT = importlib.util.find_spec('PyQt6') is not None


@unittest.skipUnless(HAVE_QT, 'PyQt6 required for actual widget tests')
class StartupWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ui
        cls.ui = ui
        # No credentials or config writes. Real widgets, one QApplication.
        with patch.object(ui.MainWindow, '_check_config', return_value=True), \
             patch.object(ui, 'QAudioOutput', side_effect=AssertionError('eager audio initialization')), \
             patch.object(ui, 'QMediaPlayer', side_effect=AssertionError('eager video initialization')):
            cls.player = ui.JarvisUI(str(Path(ui.BASE_DIR) / 'core/face_model.obj'))
        cls.window = cls.player._win
        cls.player._app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.close()
        cls.player._app.processEvents()

    def test_main_window_opens_without_media_backend(self):
        self.assertTrue(self.window.isVisible())
        self.assertIn('JARVIS-BLUE', self.window.windowTitle())
        self.assertIsNone(self.window._video_audio)
        self.assertIsNone(self.window._video_player)

    def test_setup_drawer_reaches_actual_updates_dialog(self):
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QPushButton
        from core.update_ui import UpdateDialog
        self.window._toggle_drawer(True)
        button = next(b for b in self.window._quick_drawer.findChildren(QPushButton) if 'UPDATES' in b.text())
        seen = []
        def inspect_dialog():
            for dialog in self.window.findChildren(UpdateDialog):
                seen.append(dialog.windowTitle())
                dialog.reject()
        QTimer.singleShot(50, inspect_dialog)
        # Safety timeout prevents a broken integration blocking the suite.
        QTimer.singleShot(2000, inspect_dialog)
        button.click()
        self.assertEqual(seen, ['Jarvis-Blue — Updates'])
        self.window._toggle_drawer(False)

    def test_mute_and_resize_work_before_any_video(self):
        before = self.window._muted
        self.window._toggle_mute()
        self.assertNotEqual(before, self.window._muted)
        self.window._toggle_mute()
        self.assertEqual(before, self.window._muted)
        self.window.resize(1200, 800)
        self.player._app.processEvents()
        self.assertIsNone(self.window._video_audio)

    def test_navigation_switches_pages_without_losing_home_content(self):
        self.window._show_content('Saved result', 'Keep this result')
        self.window._navigate('Quantum Lab')
        self.assertEqual(self.window._main_pages.currentIndex(), 2)
        self.assertTrue(self.window._nav_buttons['Quantum Lab'].isChecked())
        self.window._navigate('Tasks')
        self.assertEqual(self.window._main_pages.currentIndex(), 1)
        self.window._navigate('Home')
        self.assertEqual(self.window._main_pages.currentIndex(), 0)
        self.assertIn('Keep this result', self.window._content_display.toPlainText())

    def test_activity_and_arriving_results_follow_real_output(self):
        self.window._navigate('Tasks')
        self.window._refresh_activity()
        self.assertEqual(self.window._activity_text.toPlainText(),
                         self.window._log.toPlainText() or 'No activity yet.')
        self.window._show_content('New result', 'Actual tool result')
        self.assertEqual(self.window._main_pages.currentIndex(), 0)
        self.assertIn('Actual tool result', self.window._content_display.toPlainText())

    def test_status_reflects_engine_state(self):
        for state, label in [('THINKING', 'Thinking'), ('SPEAKING', 'Speaking'),
                             ('ERROR', 'Error'), ('MUTED', 'Muted')]:
            self.window._apply_state(state)
            self.assertEqual(self.window._session_status.text(), label)
        self.window._apply_state('IDLE')

    def test_navigation_opens_existing_memory_and_settings(self):
        self.window._navigate('Memory')
        self.assertTrue(self.window._memory_overlay.isVisible())
        self.window._memory_overlay.hide()
        self.window._navigate('Settings')
        self.assertTrue(self.window._quick_drawer.isVisible())
        self.window._navigate('Home')
        self.assertFalse(self.window._quick_drawer.isVisible())

    def test_coding_project_preview_and_error_guidance(self):
        import tempfile
        import time
        from PyQt6.QtCore import Qt
        panel = self.window._coding_panel
        self.window._navigate('Coding')
        self.assertEqual(self.window._main_pages.currentIndex(), 3)
        def wait_read():
            deadline = time.monotonic() + 5
            while panel._busy and time.monotonic() < deadline:
                self.player._app.processEvents()
                time.sleep(0.005)
            self.assertFalse(panel._busy, 'Background project read did not finish')
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'demo.py').write_text('print("demo")', encoding='utf-8')
            panel.select_project(directory)
            wait_read()
            self.assertEqual(panel.files.count(), 1)
            panel.files.itemDoubleClicked.emit(panel.files.item(0))
            wait_read()
            self.assertEqual(panel.preview.toPlainText(), 'print("demo")')
            panel.error_input.setPlainText('NameError: name x is not defined')
            panel._diagnose()
            self.assertIn('defined or imported', panel.diagnosis.toPlainText())
            panel.select_project(str(Path(directory, 'missing')))
            wait_read()
            self.assertIn('Could not read', panel.status.text())
        self.window._navigate('Home')

    def test_unavailable_video_keeps_window_usable(self):
        with patch.object(self.ui, 'HAVE_VIDEO', False), patch.object(self.window._log, 'append_log', wraps=self.window._log.append_log) as log:
            self.window._on_video_open('not-played.mp4', 'Unavailable', True)
            self.assertIn('not available', log.call_args.args[0])
        self.assertFalse(self.window._video_on)
        self.assertTrue(self.window.isVisible())

    def test_python_media_initialization_error_is_reported_once(self):
        try:
            with patch.object(self.ui, 'HAVE_VIDEO', True), \
                 patch.object(self.ui, 'QAudioOutput', side_effect=OSError('simulated native-library error')) as audio, \
                 patch.object(self.window._log, 'append_log', wraps=self.window._log.append_log) as log:
                self.assertFalse(self.window._ensure_video_backend())
                self.assertFalse(self.window._ensure_video_backend())
                audio.assert_called_once()
                self.assertIn('Video initialization failed', log.call_args.args[0])
            self.assertTrue(self.window.isVisible())
        finally:
            self.window._video_backend_failed = False

if __name__ == '__main__':
    unittest.main()
