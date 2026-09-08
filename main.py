import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QFileDialog, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSplitter)
from engine import compare, line_diff


def normalize(text):
    text = text.strip().strip('\"').strip("'")
    if sys.platform == 'linux' and re.match(r'^[A-Za-z]:[\\/]', text):
        text = '/mnt/' + text[0].lower() + '/' + text[3:].replace('\\', '/')
    return str(Path(text).expanduser()) if text else ''


class DropEdit(QLineEdit):
    def __init__(self):
        super().__init__()
        self.setPlaceholderText('파일·폴더 경로 붙여넣기')
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            if len(urls) != 1 or not urls[0].isLocalFile():
                return
            text = urls[0].toLocalFile()
        else:
            text = event.mimeData().text()
        self.setText(normalize(text))
        self.editingFinished.emit()
        event.acceptProposedAction()


class Panel(QWidget):
    def __init__(self, title):
        super().__init__()
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        self.path = DropEdit()
        layout.addWidget(self.path)
        buttons = QHBoxLayout()
        for label, folder in [('파일 선택', False), ('폴더 선택', True)]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, f=folder: self.choose(f))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.table = QTableWidget(0, 2)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setAcceptDrops(False)
        layout.addWidget(self.table)

    def choose(self, folder):
        value = (QFileDialog.getExistingDirectory(self, '폴더 선택') if folder
                 else QFileDialog.getOpenFileName(self, '파일 선택')[0])
        if value:
            self.path.setText(value)
            self.path.editingFinished.emit()

    def dragEnterEvent(self, event):
        self.path.dragEnterEvent(event)

    def dropEvent(self, event):
        self.path.dropEvent(event)


class Job(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, function, args):
        super().__init__()
        self.function, self.args = function, args

    def run(self):
        try:
            self.result.emit(self.function(*self.args))
        except Exception as error:
            self.failed.emit(str(error))


class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('DeployDiff — 파일과 폴더 비교')
        self.resize(1160, 740)
        self.job = None
        self.entries = []
        self.states = []
        self.folder_mode = False
        self.folder_view = False
        self.filter = '전체'
        self.folder_snapshot = None
        self.last_paths = None
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.back = QPushButton('← 뒤로')
        self.back.clicked.connect(self.go_back)
        self.back.setEnabled(False)
        self.refresh = QPushButton('새 비교')
        self.refresh.clicked.connect(self.reset_comparison)
        toolbar.addWidget(self.back)
        toolbar.addStretch()
        toolbar.addWidget(self.refresh)
        layout.addLayout(toolbar)
        self.panels = [Panel('기존 파일·폴더'), Panel('비교 파일·폴더')]
        splitter = QSplitter()
        for panel in self.panels:
            splitter.addWidget(panel)
            panel.path.editingFinished.connect(self.paths_changed)
            panel.table.cellDoubleClicked.connect(self.open_entry)
        layout.addWidget(splitter)
        self.message = QLabel('양쪽에 파일 또는 폴더를 넣으면 자동으로 비교합니다.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        filters = QHBoxLayout()
        filters.addStretch()
        self.buttons = {}
        for label in ['=', 'Diff', '전체']:
            button = QPushButton({'=': '같은 항목', 'Diff': '다른 항목', '전체': '전체 보기'}[label])
            button.setCheckable(True)
            button.setMinimumSize(100, 44)
            button.clicked.connect(lambda checked=False, value=label: self.apply_filter(value))
            self.buttons[label] = button
            filters.addWidget(button)
        filters.addStretch()
        layout.addLayout(filters)
        a, b = [p.table for p in self.panels]
        a.verticalScrollBar().valueChanged.connect(b.verticalScrollBar().setValue)
        b.verticalScrollBar().valueChanged.connect(a.verticalScrollBar().setValue)
        a.horizontalScrollBar().valueChanged.connect(b.horizontalScrollBar().setValue)
        b.horizontalScrollBar().valueChanged.connect(a.horizontalScrollBar().setValue)
        self.setStyleSheet('''
            QWidget { background:#f7f8fa; color:#202938; font-size:14px; }
            QLineEdit,QTableWidget { background:white; border:1px solid #bac4d1; }
            QLineEdit { padding:9px; }
            QPushButton { padding:8px; border:1px solid #bac4d1; border-radius:5px; }
            QPushButton:checked { background:#225bc5; color:white; }
            QHeaderView::section { background:#e9edf3; padding:6px; }
        ''')
        self.apply_filter('전체')

    def busy(self, value):
        for panel in self.panels:
            panel.setEnabled(not value)
        self.refresh.setEnabled(not value)
        self.back.setEnabled(not value and self.folder_snapshot is not None and not self.folder_view)

    @Slot()
    def paths_changed(self):
        paths = tuple(normalize(p.path.text()) for p in self.panels)
        if paths != self.last_paths:
            self.start()

    @Slot()
    def reset_comparison(self):
        """현재 비교 내용을 비우고 처음 화면으로 돌아간다."""
        if self.job and self.job.isRunning():
            return

        self.entries = []
        self.states = []
        self.folder_mode = False
        self.folder_view = False
        self.folder_snapshot = None
        self.last_paths = None
        self.current_status = ''
        self.filter = '전체'

        for side, panel in enumerate(self.panels):
            panel.path.clear()
            panel.table.clearContents()
            panel.table.setRowCount(0)
            panel.table.setHorizontalHeaderLabels(
                ['비교 결과', '파일·폴더 경로']
            )
            panel.table.setColumnHidden(0, side == 0)

        self.back.setEnabled(False)
        self.apply_filter('전체')

        self.message.setText(
            '새 비교를 시작합니다.\n'
            '왼쪽에는 기존 파일·폴더를, '
            '오른쪽에는 비교할 파일·폴더를 넣어주세요.'
        )

        self.panels[0].path.setFocus()
    def launch(self, function, args, callback):
        self.busy(True)
        self.message.setText('비교 중입니다…')
        self.job = Job(function, args)
        self.job.result.connect(callback)
        self.job.failed.connect(self.error)
        self.job.finished.connect(self.done)
        self.job.start()

    @Slot()
    def done(self):
        self.busy(False)

    @Slot(str)
    def error(self, message):
        prefix = getattr(self, 'current_status', '')
        self.message.setText((prefix + ' · ' if prefix else '') + message)

    @Slot()
    def start(self):
        if self.job and self.job.isRunning():
            return
        paths = [normalize(p.path.text()) for p in self.panels]
        self.last_paths = tuple(paths)
        for panel, path in zip(self.panels, paths):
            panel.path.setText(path)
        self.entries = []
        self.current_status = ''
        self.states = []
        self.folder_snapshot = None
        self.folder_view = False
        self.folder_mode = False
        self.back.setEnabled(False)
        for panel in self.panels:
            panel.table.setRowCount(0)
        if not all(paths):
            self.message.setText('양쪽 대상을 모두 선택해주세요.')
            return
        self.launch(compare, paths, self.compared)

    @Slot(object)
    def compared(self, result):
        self.folder_mode, self.entries = result
        if self.folder_mode:
            self.show_folders()
        else:
            self.message.setText('파일 비교: ' + self.entries[0].status)
            QTimer.singleShot(0, self.open_direct)

    def open_direct(self):
        if self.job and self.job.isRunning():
            QTimer.singleShot(10, self.open_direct)
            return
        self.open_entry(0, 0)

    def fill(self, rows, headers):
        self.states = [row[4] for row in rows]
        colors = {'동일':'#ffffff', '변경':'#fff1cb', '추가':'#dcf6e5',
                  '삭제':'#ffe2e2', '오류':'#eadfff'}
        for side, panel in enumerate(self.panels):
            panel.table.setColumnHidden(0, self.folder_view and side == 0)
            panel.table.setHorizontalHeaderLabels(headers)
            panel.table.setRowCount(len(rows))
            for i, row in enumerate(rows):
                for col in range(2):
                    cell = QTableWidgetItem(str(row[side*2+col]))
                    cell.setBackground(QColor(colors[row[4]]))
                    cell.setToolTip(str(row[side*2+col]))
                    panel.table.setItem(i, col, cell)
        self.apply_filter(self.filter)

    @Slot()
    def show_folders(self):
        self.folder_view = True
        self.back.setEnabled(False)
        rows = []
        folders = 0
        for item in self.entries:
            is_folder = any(p is not None and p.is_dir() and not p.is_symlink()
                            for p in (item.left, item.right))
            folders += int(is_folder)
            description = {
                '추가': '비교 쪽에만 있음',
                '삭제': '기존 쪽에만 있음',
                '변경': '내부에 차이 있음' if is_folder else '내용이 다름',
                '동일': '내부가 같음' if is_folder else '내용이 같음',
                '오류': '확인하지 못함',
            }[item.status]
            if item.detail and '종류' in item.detail:
                description = '파일·폴더 종류가 다름'
            values = []
            for side, path in enumerate((item.left, item.right)):
                folder = path is not None and path.is_dir() and not path.is_symlink()
                values.extend([description if side == 1 else '',
                    (item.name + ('/' if folder else '')) if path else '해당 항목 없음'])
            rows.append((*values, item.status))
        self.fill(rows, ['비교 결과', '파일·폴더 경로'])
        self.message.setText(
            f'폴더 {folders}개 · 파일 및 기타 항목 {len(rows)-folders}개\n'
            '왼쪽을 기준으로 오른쪽에 무엇이 달라졌는지 표시합니다. 원본은 수정하지 않습니다.\n'
            '초록: 비교 쪽에만 있음 / 빨강: 기존 쪽에만 있음 / 노랑: 차이 있음\n'
            '파일을 더블클릭해 내용을 확인하고, 위의 ← 뒤로 버튼으로 목록에 돌아오세요.'
        )

    @Slot()
    def go_back(self):
        if self.folder_snapshot is None or (self.job and self.job.isRunning()):
            return
        snapshot = self.folder_snapshot
        self.filter = snapshot['filter']
        self.show_folders()
        for panel, position in zip(self.panels, snapshot['positions']):
            row, vertical, horizontal = position
            if row >= 0:
                panel.table.selectRow(row)
            panel.table.verticalScrollBar().setValue(vertical)
            panel.table.horizontalScrollBar().setValue(horizontal)
        self.folder_snapshot = None

    @Slot(int, int)
    def open_entry(self, row, column):
        if self.job and self.job.isRunning():
            return
        if self.folder_mode and not self.folder_view:
            return
        if row >= len(self.entries):
            return
        entry = self.entries[row]
        self.message.setText(entry.status + ': ' + entry.detail)
        if any(p is not None and (p.is_dir() or p.is_symlink()) for p in (entry.left, entry.right)):
            self.message.setText(entry.status + ' · 폴더 또는 링크입니다. 하위 파일을 선택해주세요.')
            return
        self.current_status = entry.status
        if self.folder_mode:
            self.folder_snapshot = {
                'filter': self.filter,
                'positions': [(row, p.table.verticalScrollBar().value(),
                               p.table.horizontalScrollBar().value()) for p in self.panels],
            }
        self.launch(line_diff, (entry.left, entry.right), self.show_lines)

    @Slot(object)
    def show_lines(self, data):
        self.folder_view = False
        self.back.setEnabled(self.folder_snapshot is not None)
        self.filter = '전체'
        statuses = {'equal':'동일', 'replace':'변경', 'insert':'추가', 'delete':'삭제'}
        def visible(text):
            return text.replace('\r', '␍').replace('\n', '↵')
        rows = [(a, visible(b), c, visible(d), statuses[tag]) for a,b,c,d,tag in data]
        self.fill(rows, ['줄', '내용'])
        self.message.setText(
    f"파일 비교 결과: {self.current_status}\n"
    "색상 안내: 노랑 = 변경 / 초록 = 추가 / 빨강 = 삭제\n"
    "기호 안내: ↵ = 줄바꿈 / ␍ = CR 문자\n"
    "인코딩만 다른 경우, 파일은 ‘변경’이어도 줄 내용은 같게 표시될 수 있습니다."
)
    def apply_filter(self, value):
        self.filter = value
        for label, button in self.buttons.items():
            button.setChecked(label == value)
        for i, status in enumerate(self.states):
            hidden = (value == '=' and status != '동일') or (value == 'Diff' and status == '동일')
            for panel in self.panels:
                panel.table.setRowHidden(i, hidden)

    def closeEvent(self, event):
        if self.job and self.job.isRunning():
            self.message.setText('진행 중인 비교가 끝난 뒤 창을 닫아주세요.')
            event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    available = set(QFontDatabase.families())
    for font in ('Noto Sans CJK KR', 'Malgun Gothic', 'NanumGothic', 'Apple SD Gothic Neo'):
        if font in available:
            app.setFont(QFont(font, 10))
            break
    window = Window()
    window.show()
    sys.exit(app.exec())
