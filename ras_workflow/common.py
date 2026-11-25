from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib, json, math, os, re, time, uuid

ROOT = Path(__file__).resolve().parents[1]

def utc():
    return datetime.now(timezone.utc).isoformat()

def unique_id():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_' + uuid.uuid4().hex[:10]

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def save(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass  # Preserve the original write error for the operator.
        raise
    # If a complete replacement is locked, preserve both versions for recovery.
    for delay in (0.02, 0.05, 0.1, 0.2, 0.3, None):
        try:
            os.replace(tmp, path)
            return
        except OSError as error:
            if getattr(error, 'winerror', None) not in (32, 33) or delay is None:
                raise
            time.sleep(delay)

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()

def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def safe_path(base, value):
    p = (Path(base) / value).resolve()
    if not p.is_relative_to(ROOT): raise ValueError('Path leaves workspace: ' + str(value))
    return p

def rel(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()

def item(path, role='artifact'):
    p = safe_path(ROOT, path)
    return dict(path=rel(p), role=role, sha256=sha(p), size_bytes=p.stat().st_size)

def intact(entries):
    try:
        return bool(entries) and all(safe_path(ROOT, e['path']).is_file() and
            safe_path(ROOT, e['path']).stat().st_size == e['size_bytes'] and
            sha(safe_path(ROOT, e['path'])) == e['sha256'] for e in entries)
    except (OSError, ValueError, KeyError): return False

def code_identity():
    files=sorted((ROOT/'ras_workflow').glob('*.py'))+[ROOT/'workflow.py']
    files+=sorted(p for p in (ROOT/'ras_workflow/templates').glob('*') if p.is_file())
    files.extend(ROOT/'examples/siletz_or'/name for name in ('prepare.py','discharge.py','protocol.json'))
    return [item(p, 'workflow_code_or_template') for p in files]

def identifier(s):
    if not isinstance(s, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,47}', s):
        raise ValueError('Identifier must match [a-z][a-z0-9_]{0,47}')
    return s

def finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

@contextmanager
def lock(path):
    """Windows kernel byte-range lock: automatically released after a crash."""
    import msvcrt
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    f = path.open('a+b')
    if path.stat().st_size == 0: f.write(b'0'); f.flush()
    f.seek(0)
    try: msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close(); raise RuntimeError('Another workflow owns lock: ' + rel(path))
    try: yield
    finally:
        f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1); f.close()


def runtime_scratch():
    path = ROOT / "status" / "scratch"
    path.mkdir(parents=True, exist_ok=True)
    return path
