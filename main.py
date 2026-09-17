import os
import re
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, Slot, QTimer
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QFileDialog, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QSplitter, QFrame)
from engine import compare, line_diff
from database import save_comparison_result


def normalize(text):
    text = text.strip().strip('\"').strip("'")
    if sys.platform == 'linux' and re.match(r'^[A-Za-z]:[\\/]', text):
        text = '/mnt/' + text[0].lower() + '/' + text[3:].replace('\\', '/')
    return str(Path(text).expanduser()) if text else ''


class DropEdit(QLineEdit):
    def __init__(self):
        super().__init__()
        self.setObjectName('pathInput')
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
    def __init__(self, title, hint):
        super().__init__()
        self.setObjectName('comparisonCard')
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        title_label = QLabel(title)
        title_label.setObjectName('panelTitle')
        layout.addWidget(title_label)
        hint_label = QLabel(hint)
        hint_label.setObjectName('panelHint')
        layout.addWidget(hint_label)
        self.path = DropEdit()
        layout.addWidget(self.path)
        buttons = QHBoxLayout()
        for label, folder in [('파일 선택', False), ('폴더 선택', True)]:
            button = QPushButton(label)
            button.setProperty('variant', 'secondary')
            button.clicked.connect(lambda checked=False, f=folder: self.choose(f))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.table = QTableWidget(0, 2)
        self.table.setObjectName('resultTable')
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.horizontalHeader().setMinimumHeight(38)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
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


class StatCard(QFrame):
    def __init__(self, label, status):
        super().__init__()
        self.setObjectName('statCard')
        self.setProperty('status', status)
        self.setMinimumHeight(48)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)
        caption = QLabel(label)
        caption.setObjectName('statLabel')
        self.value = QLabel('0')
        self.value.setObjectName('statValue')
        layout.addWidget(caption)
        layout.addStretch()
        layout.addWidget(self.value)

    def set_value(self, value):
        self.value.setText(str(value))


class Window(QWidget):
    def __init__(self, history_saver=save_comparison_result):
        super().__init__()
        self.setWindowTitle('DeployDiff — 파일과 폴더 비교')
        self.resize(1160, 740)
        self.setMinimumSize(900, 620)
        self.job = None
        self.entries = []
        self.states = []
        self.folder_mode = False
        self.folder_view = False
        self.filter = '전체'
        self.folder_snapshot = None
        self.last_paths = None
        self.history_saver = history_saver
        self.history_status = ''
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)
        toolbar = QHBoxLayout()
        brand = QVBoxLayout()
        brand.setSpacing(2)
        title = QLabel('DeployDiff')
        title.setObjectName('appTitle')
        subtitle = QLabel('배포 전 파일과 폴더의 변경 사항을 한눈에 확인하세요')
        subtitle.setObjectName('appSubtitle')
        brand.addWidget(title)
        brand.addWidget(subtitle)
        toolbar.addLayout(brand)
        toolbar.addStretch()
        self.db_badge = QLabel('● DB 대기')
        self.db_badge.setObjectName('dbBadge')
        self.db_badge.setProperty('state', 'idle')
        self.back = QPushButton('← 뒤로')
        self.back.setProperty('variant', 'secondary')
        self.back.clicked.connect(self.go_back)
        self.back.setEnabled(False)
        self.refresh = QPushButton('새 비교')
        self.refresh.setObjectName('primaryButton')
        self.refresh.clicked.connect(self.reset_comparison)
        toolbar.addWidget(self.db_badge)
        toolbar.addWidget(self.back)
        toolbar.addWidget(self.refresh)
        layout.addLayout(toolbar)
        self.panels = [
            Panel('기존 버전', '현재 운영 중이거나 비교 기준이 되는 파일·폴더'),
            Panel('신규 버전', '새롭게 배포할 파일·폴더'),
        ]
        splitter = QSplitter()
        splitter.setObjectName('comparisonSplitter')
        splitter.setChildrenCollapsible(False)
        for panel in self.panels:
            splitter.addWidget(panel)
            panel.path.editingFinished.connect(self.paths_changed)
            panel.table.cellDoubleClicked.connect(self.open_entry)
        layout.addWidget(splitter)
        summary = QHBoxLayout()
        summary.setSpacing(8)
        self.stat_cards = {}
        for status, label, style in [
            ('추가', '추가된 파일', 'added'),
            ('변경', '변경된 파일', 'changed'),
            ('삭제', '삭제된 파일', 'deleted'),
            ('동일', '동일한 파일', 'same'),
        ]:
            card = StatCard(label, style)
            self.stat_cards[status] = card
            summary.addWidget(card)
        layout.addLayout(summary)
        self.message = QLabel('양쪽에 파일 또는 폴더를 넣으면 자동으로 비교합니다.')
        self.message.setObjectName('infoBanner')
        self.message.setWordWrap(True)
        self.message.setMinimumHeight(64)
        layout.addWidget(self.message)
        filters = QHBoxLayout()
        filter_title = QLabel('결과 필터')
        filter_title.setObjectName('filterTitle')
        filters.addWidget(filter_title)
        filters.addStretch()
        self.buttons = {}
        for label in ['=', 'Diff', '전체']:
            button = QPushButton({'=': '같은 항목', 'Diff': '다른 항목', '전체': '전체 보기'}[label])
            button.setCheckable(True)
            button.setMinimumSize(100, 44)
            button.setProperty('variant', 'filter')
            button.clicked.connect(lambda checked=False, value=label: self.apply_filter(value))
            self.buttons[label] = button
            filters.addWidget(button)
        layout.addLayout(filters)
        a, b = [p.table for p in self.panels]
        a.verticalScrollBar().valueChanged.connect(b.verticalScrollBar().setValue)
        b.verticalScrollBar().valueChanged.connect(a.verticalScrollBar().setValue)
        a.horizontalScrollBar().valueChanged.connect(b.horizontalScrollBar().setValue)
        b.horizontalScrollBar().valueChanged.connect(a.horizontalScrollBar().setValue)
        self.setStyleSheet('''
            QWidget { background: #f4f6fa; color: #111827; font-size: 15px; }
            QLabel#appTitle { color: #18223a; font-size: 25px; font-weight: 700; }
            QLabel#appSubtitle { color: #596579; font-size: 13px; }
            QLabel#dbBadge {
                padding: 7px 12px; background: #e9edf5; color: #68738a;
                border: 1px solid #d6deea; border-radius: 13px; font-size: 12px;
                font-weight: 700;
            }
            QLabel#dbBadge[state="success"] {
                background: #e4f7ed; color: #18794e; border-color: #bce8d0;
            }
            QLabel#dbBadge[state="error"] {
                background: #ffeded; color: #b42332; border-color: #ffc9ce;
            }
            QWidget#comparisonCard {
                background: #ffffff; border: 1px solid #dce3ef; border-radius: 12px;
            }
            QLabel#panelTitle, QLabel#filterTitle {
                background: transparent; color: #172033; font-size: 16px; font-weight: 700;
            }
            QLabel#panelHint {
                background: transparent; color: #687386; font-size: 12px;
            }
            QLineEdit#pathInput {
                min-height: 24px; padding: 10px 12px; background: #f9fbfe;
                border: 1px solid #cdd6e5; border-radius: 7px;
                selection-background-color: #486de8;
            }
            QLineEdit#pathInput:focus {
                background: #ffffff; border: 2px solid #5878e8; padding: 9px 11px;
            }
            QPushButton {
                min-height: 22px; padding: 8px 15px; background: #ffffff;
                border: 1px solid #cbd5e4; border-radius: 7px; font-weight: 600;
            }
            QPushButton:hover { background: #f0f4fb; border-color: #9eacc3; }
            QPushButton:pressed { background: #e5ebf5; }
            QPushButton:disabled { color: #a5adbb; background: #edf1f6; }
            QPushButton#primaryButton {
                color: #ffffff; background: #4568dc; border-color: #4568dc;
            }
            QPushButton#primaryButton:hover { background: #3859c7; }
            QPushButton[variant="filter"]:checked {
                color: #ffffff; background: #334fba; border-color: #334fba;
            }
            QLabel#infoBanner {
                padding: 11px 15px; background: #ffffff; color: #344054;
                border: 1px solid #d8e0eb; border-radius: 8px;
            }
            QFrame#statCard {
                background: #ffffff; border: 1px solid #d8e0eb; border-radius: 8px;
            }
            QLabel#statLabel {
                background: transparent; color: #596579; font-size: 13px;
                font-weight: 600;
            }
            QLabel#statValue {
                background: transparent; color: #18223a; font-size: 20px;
                font-weight: 700;
            }
            QFrame#statCard[status="added"] QLabel#statValue { color: #18794e; }
            QFrame#statCard[status="changed"] QLabel#statValue { color: #a15c00; }
            QFrame#statCard[status="deleted"] QLabel#statValue { color: #b42332; }
            QFrame#statCard[status="same"] QLabel#statValue { color: #536174; }
            QTableWidget#resultTable {
                background: #ffffff; alternate-background-color: #f8faff;
                border: 1px solid #d7deea; border-radius: 7px;
                gridline-color: #e5eaf2; selection-background-color: #dce6ff;
                selection-color: #172033;
            }
            QTableWidget#resultTable::item { padding: 5px; }
            QHeaderView::section {
                padding: 8px; background: #eef2f8; color: #46536b; border: 0;
                border-bottom: 1px solid #d3dbe8; font-weight: 700;
            }
            QSplitter#comparisonSplitter::handle { background: #f3f6fb; width: 12px; }
            QScrollBar:vertical { width: 10px; background: #f1f4f9; }
            QScrollBar::handle:vertical {
                min-height: 28px; background: #b8c2d3; border-radius: 5px;
            }
            QScrollBar:add-line:vertical, QScrollBar:sub-line:vertical { height: 0; }
        ''')
        self.apply_filter('전체')

    def set_db_badge(self, text, state):
        self.db_badge.setText(text)
        self.db_badge.setProperty('state', state)
        self.db_badge.style().unpolish(self.db_badge)
        self.db_badge.style().polish(self.db_badge)

    def update_summary(self, entries=()):
        counts = {status: 0 for status in self.stat_cards}
        for entry in entries:
            is_file = any(
                path is not None and (path.is_file() or path.is_symlink())
                for path in (entry.left, entry.right)
            )
            if is_file and entry.status in counts:
                counts[entry.status] += 1
        for status, card in self.stat_cards.items():
            card.set_value(counts[status])

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
        self.history_status = ''
        self.update_summary()
        self.set_db_badge('● DB 대기', 'idle')
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
        self.history_status = ''
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
        self.launch(self.compare_and_store, paths, self.compared)

    def compare_and_store(self, old_path, new_path):
        """Compare first, then try to save history without hiding the result."""
        comparison = compare(old_path, new_path)
        try:
            history_id = self.history_saver(old_path, new_path, comparison[1])
            history_status = f'DB 저장 완료 · 이력 ID {history_id}'
        except Exception as error:
            history_status = f'DB 저장 실패 · {error}'
        return comparison, history_status

    def message_with_history(self, text):
        if self.history_status and not self.history_status.startswith('DB 저장 완료'):
            return text + '\n' + self.history_status
        return text

    @Slot(object)
    def compared(self, result):
        comparison, self.history_status = result
        self.folder_mode, self.entries = comparison
        self.update_summary(self.entries)
        if self.history_status.startswith('DB 저장 완료'):
            history_id = self.history_status.rsplit(' ', 1)[-1]
            self.set_db_badge(f'● DB 저장됨  #{history_id}', 'success')
        else:
            self.set_db_badge('● DB 저장 실패', 'error')
        if self.folder_mode:
            self.show_folders()
        else:
            self.message.setText(self.message_with_history(
                '파일 비교: ' + self.entries[0].status
            ))
            QTimer.singleShot(0, self.open_direct)

    def open_direct(self):
        if self.job and self.job.isRunning():
            QTimer.singleShot(10, self.open_direct)
            return
        self.open_entry(0, 0)

    def fill(self, rows, headers):
        self.states = [row[4] for row in rows]
        colors = {'동일':'#ffffff', '변경':'#fff7df', '추가':'#e8f8ef',
                  '삭제':'#ffebed', '오류':'#f1eaff'}
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
        self.message.setText(self.message_with_history(
            f'비교 완료 · 폴더 {folders}개 · 파일 및 기타 항목 {len(rows)-folders}개\n'
            '파일을 더블클릭하면 라인 차이를 확인할 수 있습니다.  '
            '초록 추가 · 노랑 변경 · 빨강 삭제'
        ))

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
        self.message.setText(self.message_with_history(
    f"파일 비교 결과 · {self.current_status}\n"
    "노랑 변경 · 초록 추가 · 빨강 삭제  |  ↵ 줄바꿈 · ␍ CR 문자"
))
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
