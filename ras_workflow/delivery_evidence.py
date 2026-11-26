"""Retain report dependencies and reused imagery records inside Complete."""
import os
from pathlib import Path, PureWindowsPath
from xml.etree import ElementTree
from .common import ROOT, digest, read, save, sha, intact, safe_path


def dataset_links(path):
    if path.suffix.lower()=='.vrt':
        for node in ElementTree.parse(path).iter('SourceFilename'):
            if node.get('relativeToVRT')!='1':raise ValueError('VRT requires a relative, sealed raster source')
            yield node.text or ''
    elif path.name.lower().endswith('.g01.hdf'):
        import h5py
        with h5py.File(path) as opened:
            link=opened['Geometry'].attrs.get('Terrain Filename')
        if link:yield link.decode() if isinstance(link,bytes) else link
    elif path.suffix.lower()=='.hdf' and path.with_suffix('.vrt').is_file():
        # HEC-RAS stores the terrain index and the GDAL raster mosaic side by side.
        yield path.with_suffix('.vrt').name


def dataset_members(source,sources,allowed):
    """Keep relative terrain links usable. Native worker copies must match independently sealed bytes."""
    pending=[source];members={}
    while pending:
        path=pending.pop()
        if path in members:continue
        entry=sources.get(path)
        if entry is None and path.is_file():
            entry=allowed.get((path.stat().st_size,sha(path)))
        if entry is None:raise ValueError('Missing sealed terrain dependency: '+path.name)
        members[path]=entry
        for value in dataset_links(path):
            name=value.strip().replace('\\','/')
            raw=PureWindowsPath(name)
            if not name or raw.drive or raw.root or ':' in name:raise ValueError('Terrain requires a relative, sealed source')
            pending.append(safe_path(ROOT,path.parent/name))
    return members


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
        records.append(dict(source=entry))
        if source.name in follow:
            value=read(source)
            if source.name=='manifest.json' and 'native_before' in value:
                # Code/engine records are historical versions, not input artifacts.
                value={k:value[k] for k in ('source_inputs','input_snapshots','native_before',
                    'native_after','outputs','execution') if k in value}
            queue.extend(entries(value))
    def include(source,entry,destination):
        nonlocal total
        path=full/destination
        if not path.exists():
            total+=entry['size_bytes']
            if total>limit:raise ValueError('Complete-package evidence budget exceeded')
            copy_file(source,path)
        if sha(path)!=entry['sha256']:raise ValueError('Packaged source differs: '+entry['path'])
        by_hash.setdefault(entry['sha256'],destination)
        return destination

    sources_by_path={safe_path(ROOT,row['source']['path']):row['source'] for row in records}
    dataset_paths={}
    allowed={(e['size_bytes'],e['sha256']):e for e in sources_by_path.values()}
    for source in sources_by_path:
        if source.suffix.lower()!='.vrt' and not source.name.lower().endswith('.g01.hdf'):continue
        members=dataset_members(source,sources_by_path,allowed)
        existing=by_hash.get(sources_by_path[source]['sha256'])
        if existing:
            parent=(full/existing).parent
            neighbors={p:(parent/os.path.relpath(p,source.parent)).resolve() for p in members}
            if all(f.is_relative_to(full.resolve()) and f.is_file() and sha(f)==members[p]['sha256']
                   for p,f in neighbors.items()):
                dataset_paths[source]=existing
                continue
        parent=Path(os.path.commonpath([p.parent for p in members]))
        layout={p.relative_to(parent).as_posix():e['sha256'] for p,e in members.items()}
        group='Evidence/ReportSources/'+digest(layout)+'/'
        for path,entry in members.items():
            target=include(path,entry,group+path.relative_to(parent).as_posix())
            if path==source or path.suffix.lower()=='.vrt':dataset_paths[path]=target
    for row in records:
        entry=row['source'];source=safe_path(ROOT,entry['path'])
        target=dataset_paths.get(source) or by_hash.get(entry['sha256'])
        if target is None:
            target=include(source,entry,'Evidence/ReportSources/'+entry['sha256']+'/'+source.name)
        row['package_path']=target
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
