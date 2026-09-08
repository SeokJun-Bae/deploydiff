import tempfile
import unittest
from pathlib import Path
from engine import compare, line_diff


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a = Path(self.temp.name) / 'left'
        self.b = Path(self.temp.name) / 'right'
        self.a.mkdir()
        self.b.mkdir()

    def test_directory_status_and_empty_folders(self):
        for root in (self.a, self.b):
            (root / 'config').mkdir()
            (root / 'same').write_bytes(b'same')
        (self.a / 'config/app').write_bytes(b'abcd')
        (self.b / 'config/app').write_bytes(b'efgh')
        (self.a / 'removed').mkdir()
        (self.b / 'added').mkdir()
        folder, rows = compare(self.a, self.b)
        self.assertTrue(folder)
        self.assertEqual({r.name:r.status for r in rows}, {
            'config':'변경', 'config/app':'변경', 'same':'동일',
            'removed':'삭제', 'added':'추가'})

    def test_line_insertion_alignment(self):
        a, b = self.a/'a', self.b/'b'
        a.write_bytes(b'one\ntwo\n')
        b.write_bytes(b'one\nnew\ntwo\n')
        rows = line_diff(a, b)
        self.assertEqual([r[4] for r in rows], ['equal', 'insert', 'equal'])
        self.assertEqual(rows[-1][:4], (2,'two\n',3,'two\n'))

    def test_line_endings_are_changes(self):
        a, b = self.a/'a', self.b/'b'
        a.write_bytes(b'hello\r\n')
        b.write_bytes(b'hello\n')
        self.assertEqual(compare(a,b)[1][0].status, '변경')
        self.assertEqual(line_diff(a,b)[0][4], 'replace')

    def test_binary_rejected_for_lines(self):
        a = self.a/'binary'
        a.write_bytes(b'\x00\x01')
        with self.assertRaises(ValueError):
            line_diff(a,a)
        self.assertEqual(compare(a,a)[1][0].status, '동일')

    def test_added_text(self):
        b = self.b/'new'
        b.write_text('새 파일', encoding='utf-8')
        self.assertEqual(line_diff(None,b)[0][4], 'insert')

    def test_invalid_input(self):
        with self.assertRaises(OSError):
            compare(self.a/'missing', self.b)

    def test_type_change(self):
        (self.a/'item').mkdir()
        (self.b/'item').write_bytes(b'file')
        self.assertEqual(compare(self.a,self.b)[1][0].status, '변경')


if __name__ == '__main__':
    unittest.main()
