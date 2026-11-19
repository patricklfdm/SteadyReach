"""Retain report dependencies and reused imagery records inside Complete."""
from pathlib import Path
from .common import ROOT, read, save, sha, intact, safe_path


def archive_report_sources(full, sources, limit):
    """Resolve hashed references, deduplicate bytes, and index historical paths."""
    from .report_catalog import entries
    from .site_delivery import copy_file
    full=Path(full);queue=list(sources);seen={};records=[]
    by_hash={};total=0
    for path in full.rglob('*'):
        if path.is_file():
            total+=path.stat().st_size
            by_hash.setdefault(sha(path),path.relative_to(full).as_posix())
    if total>limit:raise ValueError('Complete-package evidence budget exceeded')
    follow={'summary.json','diagnostics.json','native_supplement.json','bundle.json',
            'receipt.json','execution.json','manifest.json'}
    while queue:
        entry=queue.pop(0);source=safe_path(ROOT,entry['path'])
        identity=(entry['sha256'],entry['size_bytes'])
        if entry['path'] in seen:
            if seen[entry['path']]!=identity:raise ValueError('Conflicting report evidence identities')
            continue
        seen[entry['path']]=identity
        if not intact([entry]):raise ValueError('Report dependency changed: '+entry['path'])
        destination=by_hash.get(entry['sha256'])
        if destination is None:
            total+=entry['size_bytes']
            if total>limit:raise ValueError('Complete-package evidence budget exceeded')
            destination='Evidence/ReportSources/'+entry['sha256']+'/'+source.name
            copy_file(source,full/destination);by_hash[entry['sha256']]=destination
        records.append(dict(source=entry,package_path=destination))
        if source.name in follow:
            value=read(source)
            if source.name=='manifest.json' and 'native_before' in value:
                # Code/engine records are historical versions, not input artifacts.
                value={k:value[k] for k in ('source_inputs','input_snapshots','native_before',
                    'native_after','outputs','execution') if k in value}
            queue.extend(entries(value))
    result=dict(schema_version='delivery_report_sources_1.0',entries=records,
        scope='Historical workspace paths map to exact files inside this package; no new calculation.',
        hydraulic_qa='REVIEW_REQUIRED',engineering_acceptance='NOT_ASSESSED')
    save(full/'Evidence/ReportSources/index.json',result)
    for row in records:
        file=(full/row['package_path']).resolve()
        if not file.is_relative_to(full.resolve()) or sha(file)!=row['source']['sha256']:
            raise ValueError('Archived report dependency mismatch')
    return result


def preserve_imagery_records(acquired,full):
    """Follow old receipt links only until a sealed acquisition folder is found."""
    from .site_delivery import copy_file
    current=acquired;visited=set();receipts=[]
    while current.get('previous_manifest') and current.get('previous_receipt'):
        manifest=current['previous_manifest'];receipt=current['previous_receipt']
        if not intact([manifest,receipt]):raise ValueError('Previous imagery evidence changed')
        path=safe_path(ROOT,manifest['path'])
        if str(path) in visited:raise ValueError('Cyclic imagery provenance')
        visited.add(str(path));receipts.append(dict(manifest=manifest,receipt=receipt))
        records=[e for e in read(path)['files'] if e['path'].startswith('Evidence/Imagery/')]
        if records:
            for e in records:
                source=(path.parent/e['path']).resolve()
                destination=(Path(full)/e['path']).resolve()
                if (not source.is_relative_to(path.parent) or source.is_symlink()
                    or not destination.is_relative_to(Path(full).resolve())):raise ValueError('Unsafe imagery evidence path')
                if source.stat().st_size!=e['size_bytes'] or sha(source)!=e['sha256']:
                    raise ValueError('Cached imagery acquisition record changed')
                copy_file(source,destination)
            # A larger mosaic may have been justified by a second live query.
            # Carry that query forward when this edition reuses the same map.
            query_dir=Path(full)/'Evidence/ImageryQuery'
            if not query_dir.exists():
                for e in read(path)['files']:
                    if e['path'].startswith('Evidence/ImageryQuery/'):
                        source=safe_path(path.parent,e['path'])
                        if not source.is_relative_to(path.parent/'Evidence/ImageryQuery') or sha(source)!=e['sha256']:
                            raise ValueError('Cached imagery selection evidence changed')
                        copy_file(source,query_dir/source.relative_to(path.parent/'Evidence/ImageryQuery'))
            # Preserve each receipt traversed; prior packages need not be retained.
            for i,pair in enumerate(receipts):
                for role,e in pair.items():copy_file(ROOT/e['path'],Path(full)/'Evidence/ImageryReuse'/str(i)/(role+'.json'))
            save(Path(full)/'Evidence/ImageryReuse/index.json',dict(receipts=receipts,
                acquisition_records=len(records),network_requests=0))
            return len(records)
        current=read(ROOT/receipt['path'])
    raise ValueError('Reused imagery acquisition files are unavailable; retain or restore its earlier complete package')
