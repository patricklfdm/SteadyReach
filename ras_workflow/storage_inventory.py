"""A conservative file-ownership inventory for one local edition."""
from functools import lru_cache
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from .common import digest, identifier, read, sha

# Published packages can be used outside SteadyReach and remain online.
GENERATED={'approved':'calculation','exports':'export','studies':'study','geometry_comparisons':'study',
           'automatic_preparation':'preview','sensitivity_suggestions':'preview','check_batches':'study',
           'preparation':'preview','reviews':'review','context_layers':'cache'}
SKIP_METADATA={'Complete','Minimal','inputs_before','ReportSources','InputFiles'}
PATH_VALUE=re.compile(rb'"((?:(?:projects|data|examples|status)[/\\]|\.\.[/\\]|[a-zA-Z]:[/\\])(?:[^"\\]|\\.)*)"')
PREFIXES=('projects','data','status','examples')


RUNTIME_LOCKS={'apply.lock','browser_draft.lock','browser.lock','confirm.lock','cycle.lock','fetch.lock','intake.lock',
               'pdf_recovery.lock','project.lock','queue.lock','recipient_handoff.lock','session.lock','study.lock'}


def regular_tree(folder,locks=None,metadata_only=False):
    """Return regular files; links, including junctions, cannot enter a cleanup."""
    result={}
    stack=[(folder,False)]
    while stack:
        directory,ignored=stack.pop()
        if directory.is_symlink() or directory.is_junction():
            raise ValueError('Linked storage directory: '+str(directory))
        with os.scandir(directory) as entries:
            for e in entries:
                s=e.stat(follow_symlinks=False)
                if getattr(s,'st_file_attributes',0)&1024 or e.is_symlink():
                    raise ValueError('Linked storage member: '+e.path)
                if e.is_dir(follow_symlinks=False):
                    skip=metadata_only and (ignored or e.name in SKIP_METADATA or e.name.startswith('Handoff_'))
                    stack.append((Path(e.path),skip))
                elif e.name in RUNTIME_LOCKS:
                    if locks is not None:locks.add(Path(e.path))
                elif not metadata_only or (not ignored and e.name.lower().endswith('.json')):
                    result[Path(e.path)]=s
    return result


def _path_values(data):
    return tuple(json.loads(b'"'+raw+b'"').replace('\\','/') for raw in set(PATH_VALUE.findall(data)))


# Key on actual bytes, so an externally edited JSON with the same size and mtime
# is re-parsed. Cap retained input at 8 MiB; large documents bypass the cache.
_cached_paths=lru_cache(maxsize=256)(_path_values)


def references(root,folder,files):
    targets=set()
    known=set()
    # All paths originate in regular_tree. That traversal checks every member for links.
    # Compare path components using host filesystem case semantics and a separator.
    root_prefix=os.path.join(os.path.normcase(str(root)),'')
    own_prefix=os.path.join(os.path.normcase(str(folder)),'')
    depth=len(folder.parts)
    for path in files:
        if path.suffix.lower()!='.json':
            continue
        parts=path.parts[depth:]
        if any(p in SKIP_METADATA or p.startswith('Handoff_') for p in parts):
            continue
        data=path.read_bytes()
        for value in (_cached_paths(data) if len(data)<=32768 else _path_values(data)):
            base=path.parent if value.startswith('../') else root
            if (base,value) in known:continue
            known.add((base,value))
            if any(c in value for c in '\x00\r\n*?"<>|') or len(value)>2048:continue
            absolute=os.path.abspath(os.path.join(base,value))
            normalized=os.path.normcase(absolute)
            if not normalized.startswith(root_prefix) or normalized.startswith(own_prefix) or normalized==own_prefix[:-1]:
                continue
            ref=Path(absolute)
            relative=ref.parts[len(root.parts):]
            if len(relative)>=2 and relative[0] in PREFIXES and relative[:2] not in (('status','app'),('status','edition_storage')):
                targets.add(ref)
    return targets


def classify(relative):
    if any(p.startswith('Handoff_') or p in ('Complete','Minimal') for p in relative):
        return 'reports' if 'Reports' in relative else 'delivery'
    return GENERATED.get(relative[0],'inputs')


def inspect(root,key):
    root=Path(root).resolve();folder=root/'projects'/identifier(key)
    model=read(folder/'app.json')
    local=regular_tree(folder)
    refs=references(root,folder,local)
    sources=set()
    # An imported original can itself be located under a generated directory.
    registered=[*model.get('attachments',[]),*model.get('input_choices',[]),*(model.get('terrain') or {}).values()]
    missing=set()
    for row in registered:
        if not isinstance(row,dict) or not row.get('path'):continue
        source=(root/row['path']).resolve();sources.add(source)
        if (not source.is_relative_to(root) or not source.is_file() or source.relative_to(root).parts[0] not in PREFIXES
                or (row.get('sha256') and sha(source)!=row['sha256'])):
            missing.add(row['path'])
        elif not source.is_relative_to(folder):refs.add(source)
    referenced=set();dependents=set()
    for app in sorted((root/'projects').glob('*/app.json')):
        other=app.parent
        if other==folder:continue
        meta=read(app)
        paths=references(root,other,regular_tree(other,metadata_only=True))
        if (meta.get('parent_revision') or {}).get('project_id')==key or any(p.is_relative_to(folder) for p in paths):
            dependents.add(other.name)
        referenced.update(paths)
    # Cold children still need their parents even when a study's metadata is offline.
    for record in (root/'status/edition_storage').glob('*/state.json'):
        state=read(record)
        if state.get('phase') in ('RETIRING','ARCHIVED','RESTORING') and key in state.get('parents',[]):
            dependents.add(record.parent.name)
    parents=set()
    parent=(model.get('parent_revision') or {}).get('project_id')
    if parent:parents.add(parent)
    external={}
    for ref in refs:
        rel=ref.relative_to(root).parts
        if rel[0]=='projects':parents.add(rel[1])
        if not ref.exists():continue  # Old evidence may include historical workspace paths.
        if ref.resolve()!=ref or ref.is_symlink() or ref.is_junction():raise ValueError('Linked dependency: '+str(ref))
        # Files referenced from another edition remain owned by that edition.
        if ref.is_file():external[ref]=ref.stat()
        elif ref.is_dir() and rel[0]=='data':
            external.update(regular_tree(ref))
    counts=defaultdict(lambda: Counter(files=0,bytes=0))
    reclaim=[];logical=exclusive=shared=0
    entries={}
    directory_use={}
    def used_by_others(path):
        if path in referenced:
            return True
        parent=path.parent
        if parent not in directory_use:
            directory_use[parent]=any(p in referenced for p in (parent,*parent.parents))
        return directory_use[parent]
    for path,s in sorted({**local,**external}.items()):
        name=path.relative_to(root).as_posix()
        own=path in local
        kind=classify(path.relative_to(folder).parts) if own else 'dependency'
        if kind in ('inputs','dependency') and path.suffix.lower() in ('.tif','.tiff') and any(
                word in name.lower() for word in ('terrain','dem','3dep')) and 'imagery' not in name.lower():
            kind='terrain'
        counts[kind]['files']+=1;counts[kind]['bytes']+=s.st_size
        logical+=s.st_size
        multi=(not own and name.startswith('projects/')) or used_by_others(path) or (s.st_nlink or path.stat().st_nlink)>1
        if multi:
            shared+=s.st_size;counts[kind]['shared_bytes']+=s.st_size
        else:exclusive+=s.st_size
        entries[name]=(s.st_size,s.st_mtime_ns)
        if own and kind in GENERATED.values() and not sources.intersection((path,*path.parents)) and not multi:
            reclaim.append(name)
            counts[kind]['candidate_bytes']+=s.st_size
    total=sum(entries[n][0] for n in reclaim)
    token=digest(dict(entries=entries,dependents=sorted(dependents),parents=sorted(parents),missing=sorted(missing),reclaim=reclaim))
    return dict(id=key,title=model['title'],revision=model['revision'],token=token,logical_bytes=logical,
                exclusive_bytes=exclusive,shared_bytes=shared,groups=dict(counts),candidate_bytes=total,
                reclaimable_bytes=0 if dependents or missing else total,dependents=sorted(dependents),parents=sorted(parents),
                unverified_sources=sorted(missing),
                files=entries,reclaim=reclaim)
