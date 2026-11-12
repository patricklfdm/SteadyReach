"""Append-only report registration outside sealed attempts; old receipts stay immutable."""
from .common import ROOT, digest, intact, item, lock, read, rel, safe_path, save, utc


def catalog_path(summary):
    # Mutable registration is outside immutable attempt/queue directories.
    return ROOT/'status/report_catalogs'/digest(rel(summary))/'catalog.json'


def entries(value):
    if isinstance(value, dict):
        if {'path', 'sha256', 'size_bytes'} <= value.keys():
            yield value
        else:
            for child in value.values(): yield from entries(child)
    elif isinstance(value, list):
        for child in value: yield from entries(child)


def validate(summary, manifest):
    summary, manifest = [safe_path(ROOT, p) for p in (summary, manifest)]
    m = read(manifest)
    if m.get('summary') != item(summary, 'sole_report_data'):
        raise ValueError('Report belongs to another summary')
    if not m.get('reports') or not intact(list(entries(m))):
        raise ValueError('Report files or sources changed')
    return m


def register(summary, manifest):
    summary, manifest = [safe_path(ROOT, p) for p in (summary, manifest)]
    validate(summary, manifest)
    path = catalog_path(summary); path.parent.mkdir(parents=True, exist_ok=True)
    with lock(path.parent/'catalog.lock'):
        data = read(path) if path.exists() else dict(schema_version='report_catalog_1.0', summary=item(summary), editions=[])
        if data['summary'] != item(summary): raise ValueError('Report catalogue summary changed')
        entry = item(manifest)
        if entry not in [e['manifest'] for e in data['editions']]:
            data['editions'].append(dict(registered_utc=utc(), manifest=entry))
        save(path, data)
    return entry


def inspect(summary):
    summary = safe_path(ROOT, summary); path = catalog_path(summary)
    editions = []; issues = []
    original = summary.parent/'reports/report_manifest.json'
    if original.exists(): editions.append(dict(registered_utc=None, manifest=item(original)))
    if path.exists():
        try:
            data = read(path)
            if data['summary'] != item(summary): raise ValueError('Catalogue summary mismatch')
            editions += data['editions']
        except (ValueError, KeyError, TypeError, OSError) as e: issues.append('REPORT_CATALOG_CHANGED: '+str(e))
    history = []; seen = set()
    for edition in editions:
        if not isinstance(edition,dict) or not isinstance(edition.get('manifest'),dict) or not isinstance(edition['manifest'].get('path'),str):
            issues.append('REPORT_CATALOG_CHANGED: malformed edition');continue
        e = edition['manifest']
        if e['path'] in seen: continue
        seen.add(e['path']); record = dict(edition, verified=False)
        try:
            if not intact([e]): raise ValueError('Manifest changed')
            record['content'] = validate(summary, ROOT/e['path']); record['verified'] = True
        except (ValueError, KeyError, TypeError, OSError) as err:
            record['error'] = str(err); issues.append('REPORT_EDITION_CHANGED: '+e['path'])
        history.append(record)
    valid = [e for e in history if e['verified']]
    return dict(history=history, latest=valid[-1] if valid else None, issues=issues)
