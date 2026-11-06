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
