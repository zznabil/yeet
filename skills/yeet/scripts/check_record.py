"""Check yeet records: Python literal files, <=200 non-blank lines and <=500 words."""
import ast
from pathlib import Path
import sys

MAX_LINES, MAX_WORDS = 200, 500
KINDS = {'spec', 'state', 'handoff', 'archive', 'doc'}
KEYS = {'kind', 'id', 'prev', 'next', 'body'}


def check(path, root=None):
    """Return error strings for one record file."""
    path = Path(path)
    root = Path(root) if root else path.parent
    text = path.read_text(encoding='utf-8')
    errors = []
    lines = sum(1 for line in text.splitlines() if line.strip())
    if lines > MAX_LINES:
        errors.append(f'{path}: {lines} lines > {MAX_LINES}')
    words = len(text.split())
    if words > MAX_WORDS:
        errors.append(f'{path}: {words} words > {MAX_WORDS}')
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return errors + [f'{path}: syntax error line {error.lineno}']
    is_doc = lambda n: isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) \
        and isinstance(n.value.value, str)
    body = [n for n in tree.body if not is_doc(n)]
    imp = body[:1]
    if not (len(imp) == 1 and isinstance(imp[0], ast.ImportFrom) and imp[0].module == 'record'
            and imp[0].level == 0 and [a.name for a in imp[0].names] == ['Record']):
        return errors + [f'{path}: first statement must be `from record import Record`']
    body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.AnnAssign) or \
            getattr(body[0].target, 'id', None) != 'RECORD' or \
            getattr(body[0].annotation, 'id', None) != 'Record' or body[0].value is None:
        return errors + [f'{path}: then exactly one `RECORD: Record = {{...}}`']
    try:
        record = ast.literal_eval(body[0].value)
    except ValueError:
        return errors + [f'{path}: RECORD is not a pure literal (no calls, names, logic)']
    if not isinstance(record, dict) or set(record) != KEYS:
        return errors + [f'{path}: RECORD keys must be exactly {sorted(KEYS)}']
    if record['kind'] not in KINDS:
        errors.append(f'{path}: kind must be one of {sorted(KINDS)}')
    if not isinstance(record['id'], str) or not record['id']:
        errors.append(f'{path}: id must be a non-empty string')
    for link in ('prev', 'next'):
        value = record[link]
        if value is not None and not (root / value).is_file():
            errors.append(f'{path}: {link} not found: {value}')
    return errors


def main(argv):
    root = Path(argv[1] if len(argv) > 1 else '.yeet')
    files = sorted(f for f in root.rglob('*.py') if f.name != 'record.py') if root.is_dir() else [root]
    errors = [e for f in files for e in check(f, root if root.is_dir() else None)]
    print('\n'.join(errors) if errors else f'PASS: {len(files)} record(s)')
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
