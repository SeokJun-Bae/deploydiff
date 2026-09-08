"""Run with QT_QPA_PLATFORM=offscreen for a headless smoke test."""
import tempfile
import time
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from main import Window


class GuiTest(unittest.TestCase):
    def test_compare_open_filter_and_return(self):
        app = QApplication.instance() or QApplication([])
        window = Window()
        def wait_for(predicate):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                app.processEvents()
                if predicate():
                    return
                time.sleep(.01)
            self.fail('GUI operation timed out')
        with tempfile.TemporaryDirectory() as temp:
            roots = [Path(temp)/name for name in ('left', 'right')]
            for root in roots:
                root.mkdir()
            (roots[0]/'test.txt').write_text('one\ntwo\n')
            (roots[1]/'test.txt').write_text('one\nnew\ntwo\n')
            for panel, root in zip(window.panels, roots):
                panel.path.setText(str(root))
            window.start()
            wait_for(lambda: window.folder_view and not window.job.isRunning())
            self.assertEqual(window.panels[0].table.rowCount(), 1)
            window.open_entry(0,0)
            wait_for(lambda: not window.folder_view and not window.job.isRunning())
            self.assertEqual(window.panels[0].table.rowCount(), 3)
            window.apply_filter('Diff')
            self.assertTrue(window.panels[0].table.isRowHidden(0))
            self.assertFalse(window.panels[1].table.isRowHidden(1))
            window.show_folders()
            self.assertEqual(window.panels[0].table.rowCount(), 1)
            for panel, root in zip(window.panels, roots):
                panel.path.setText(str(root/'test.txt'))
            window.start()
            wait_for(lambda: not window.folder_mode and window.panels[0].table.rowCount()==3 and not window.job.isRunning())
            window.close()


if __name__ == '__main__':
    unittest.main()
