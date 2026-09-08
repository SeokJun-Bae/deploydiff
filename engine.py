"""Read-only directory and line comparison, independent of Qt."""
from dataclasses import dataclass
from pathlib import Path
from difflib import SequenceMatcher
import os


@dataclass
class Entry:
    name: str
    left: Path | None
    right: Path | None
    status: str
    detail: str = ''


def same_bytes(a, b):
    if a.stat().st_size != b.stat().st_size:
        return False
    with a.open('rb') as x, b.open('rb') as y:
        while True:
            chunk = x.read(1024 * 1024)
            if chunk != y.read(1024 * 1024):
                return False
            if not chunk:
                return True


def kind(p):
    if p.is_symlink():
        return 'link'
    if p.is_dir():
        return 'folder'
    if p.is_file():
        return 'file'
    raise OSError(f'지원하지 않거나 접근할 수 없는 경로: {p}')


def scan(root):
    found = {}
    def fail(error):
        raise error
    for current, dirs, files in os.walk(root, followlinks=False, onerror=fail):
        for name in dirs + files:
            p = Path(current) / name
            found[p.relative_to(root).as_posix()] = p
    return found


def compare(left, right):
    a, b = Path(left).expanduser().resolve(), Path(right).expanduser().resolve()
    ka, kb = kind(a), kind(b)
    if ka != kb or ka not in ('file', 'folder'):
        raise ValueError('파일은 파일과, 폴더는 폴더와 비교해주세요.')
    if ka == 'file':
        return False, [Entry(a.name + ' ↔ ' + b.name, a, b,
                             '동일' if same_bytes(a, b) else '변경')]
    x, y = scan(a), scan(b)
    rows = []
    for name in sorted(x.keys() | y.keys()):
        p, q = x.get(name), y.get(name)
        status, detail = '동일', ''
        try:
            if p is None:
                status = '추가'
            elif q is None:
                status = '삭제'
            elif kind(p) != kind(q):
                status, detail = '변경', '파일/폴더 종류가 바뀌었습니다.'
            elif kind(p) == 'link':
                status = '동일' if os.readlink(p) == os.readlink(q) else '변경'
            elif kind(p) == 'file':
                status = '동일' if same_bytes(p, q) else '변경'
        except OSError as error:
            status, detail = '오류', str(error)
        rows.append(Entry(name, p, q, status, detail))
    by_name = {r.name: r for r in rows}
    for row in reversed(rows):
        if row.status != '동일':
            for parent in Path(row.name).parents:
                ancestor = by_name.get(parent.as_posix())
                if ancestor and ancestor.status == '동일':
                    ancestor.status = '오류' if row.status == '오류' else '변경'
    return True, rows


def read_text(path):
    if path is None:
        return []
    if path.is_symlink() or not path.is_file():
        raise ValueError('일반 텍스트 파일만 줄 비교를 지원합니다.')
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError('2 MiB를 초과하는 파일은 동일 여부만 표시합니다.')
    data = path.read_bytes()
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = data.decode('utf-16')
    else:
        if b'\x00' in data:
            raise ValueError('바이너리 파일은 동일 여부만 표시합니다.')
        for encoding in ('utf-8-sig', 'cp949'):
            try:
                text = data.decode(encoding)
                break
            except UnicodeDecodeError:
                pass
        else:
            raise ValueError('지원하는 텍스트 인코딩이 아닙니다.')
    lines = text.splitlines(keepends=True)
    if len(lines) > 10000:
        raise ValueError('10,000줄을 초과하는 파일은 동일 여부만 표시합니다.')
    return lines


def line_diff(left, right):
    a, b = read_text(left), read_text(right)
    rows = []
    for tag, i, j, k, l in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        for offset in range(max(j-i, l-k)):
            x, y = i + offset, k + offset
            rows.append((x+1 if x<j else '', a[x] if x<j else '',
                         y+1 if y<l else '', b[y] if y<l else '', tag))
    return rows
