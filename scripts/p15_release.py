"""Measure edition ownership, archive and restore on an isolated growing project catalog."""
import argparse
import errno
import hashlib
import importlib.util
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ras_workflow import edition_storage, storage_capacity, storage_inventory
from ras_workflow.common import digest, read, save, sha, unique_id
from ras_workflow.site_delivery import verify


def previous(root,name):
    path=root/'ras_workflow'/(name+'.py')
    expected={'storage_inventory':'2a5b8f77916f41cd184b2011cf313069bff9e8ef2e65b65ba0d849898c394079',
              'edition_storage':'01c7996e4e40a3ab68ab7f9884c588c57ebcd724489c2e46e5d31742493c99e5'}
    if hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected[name]:
        raise ValueError('The reference must match the 8781730 storage implementation')
    spec=importlib.util.spec_from_file_location('ras_workflow.p15_reference_'+name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def timed(action):
    start=time.perf_counter()
    result=action()
    return result,round(time.perf_counter()-start,4)


def cycle(storage, root, key, archive_dir, inventory, interrupt=False):
    def action(name, **args):
        return storage.perform(root,key,name,dict(confirmed=True,**args))
    archive_dir.mkdir()
    body=dict(token=inventory['token'],directory=str(archive_dir))
    free_before=shutil.disk_usage(root).free
    archive,write=timed(lambda:action('archive',**body))
    receipt,retire=timed(lambda:action('retire',**body,archive_hash=archive['sha256']))
    net_volume_change=shutil.disk_usage(root).free-free_before
    removed=sum(inventory['files'][n][0] for n in inventory['reclaim'] if not (root/n).exists())
    assert removed==inventory['reclaimable_bytes']>0
    recovered=dict(archive_hash=archive['sha256'])
    if interrupt:
        real=storage.restore_file
        writes=[]
        def fail_second(path,source,row):
            if writes:
                raise OSError(errno.ENOSPC,'Injected disk-full during isolated restoration')
            real(path,source,row)
            writes.append(path)
        with patch.object(storage,'restore_file',fail_second):
            try:action('restore',**recovered)
            except OSError as error:
                if error.errno!=errno.ENOSPC:raise
            else:raise ValueError('Expected mid-restore interruption')
        assert len(writes)==1 and storage.state(root,key)['phase']=='RESTORING'
    result,restore=timed(lambda:action('restore',**recovered))
    assert result['phase']=='ONLINE'
    return dict(archive_s=write,retire_s=retire,restore_s=restore,archive_bytes=archive['archive_bytes'],
                retired_member_bytes=removed,volume_gain_bytes=receipt['actual_volume_gain'],
                net_volume_change_after_archive_and_retire=net_volume_change,restored_files=result['restored_files'],resumed=interrupt)


def run(source,reference):
    old=previous(reference,'storage_inventory')
    old_storage=previous(reference,'edition_storage')
    old_storage.inspect=old.inspect
    old_storage.regular_tree=old.regular_tree
    key=source['baseline']
    original=storage_inventory.inspect(ROOT,key)
    out=ROOT/'status/p15'/unique_id()
    out.mkdir(parents=True)
    result=dict(status='RUNNING',case=key,reference_hashes={n:sha(reference/'ras_workflow'/(n+'.py'))
                for n in ('storage_inventory','edition_storage')},tiers=[],human='DEFERRED',cross_machine='DEFERRED')
    try:
        from midway_release import page_action
        import json
        result['capacity_page']=json.loads(page_action(key,'p15-capacity'))
        with tempfile.TemporaryDirectory(dir=out) as tmp:
            base=Path(tmp);work=base/'work'
            for name in original['files']:
                dest=work/name;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/name,dest)
            local=work/'projects'/key
            summary=read(work/read(local/'app.json')['summary']['path'])
            hdf=summary['hydraulics']['raw_hdf']
            assert sha(work/hdf['path'])==hdf['sha256']
            result['native_hdf_sha256']=hdf['sha256']
            # Use actual metadata and output directory shapes as the background load.
            # Only the selected edition contains a real native job. Peers are storage fixtures.
            samples=[p for p in local.rglob('*.json') if p.stat().st_size<32768 and p.name!='app.json'
                     and not set(p.relative_to(local).parts)&storage_inventory.SKIP_METADATA][:10]
            assert len(samples)==10
            result['peer_metadata_samples']=[p.relative_to(local).as_posix() for p in samples]
            shared='data/shared/ownership_probe.txt'
            save(local/'storage_probe.json',{'path':shared})
            probe=work/shared;probe.parent.mkdir(parents=True,exist_ok=True);probe.write_bytes(b'P15 shared dependency')
            hashes={n:sha(work/n) for n in storage_inventory.inspect(work,key)['files']}
            peers=0
            for count in (1,24,171):
                while peers<count-1:
                    peers+=1
                    peer='catalog_'+str(peers)
                    folder=work/'projects'/peer
                    save(folder/'app.json',dict(id=peer,title='Catalog fixture',revision=1,shared=shared))
                    for sample in samples:
                        dest=folder/sample.relative_to(local)
                        dest.parent.mkdir(parents=True,exist_ok=True)
                        dest.write_bytes(sample.read_bytes().replace(key.encode(),peer.encode()))
                    for name in ('Complete','Minimal'):
                        dst=folder/'exports'/name/'Reports';dst.mkdir(parents=True,exist_ok=True)
                        (dst/'index.json').write_bytes(b'{}')
                tier=dict(editions=count,methods={})
                result['tiers'].append(tier)
                # Alternate order across sweeps, using exactly the same disk contents.
                samples_s={'previous':[],'candidate':[]}
                for order in (('previous','candidate'),('candidate','previous'),('previous','candidate')):
                    for name in order:
                        module=old if name=='previous' else storage_inventory
                        inv,elapsed=timed(lambda:module.inspect(work,key))
                        samples_s[name].append(elapsed)
                        if name=='previous':
                            previous_inv=inv
                        else:
                            if inv!=previous_inv:raise ValueError('Inventory or candidate list changed')
                tier['inventory_sha256']=digest(inv)
                tier['shared_bytes']=inv['shared_bytes']
                if count==24 and inv['shared_bytes']!=result['tiers'][0]['shared_bytes']+probe.stat().st_size:
                    raise ValueError('Shared ownership of the external file did not change')
                for name,storage in [('previous',old_storage),('candidate',edition_storage)]:
                    row=cycle(storage,work,key,base/f'archive_{count}_{name}',inv)
                    tier['methods'][name]=dict(row,inventory_s=samples_s[name],median_inventory_s=statistics.median(samples_s[name]))
                    assert all(sha(work/n)==h for n,h in hashes.items())
                if count==171:
                    tier['interrupted_restore']=cycle(edition_storage,work,key,base/'fault',inv,True)
                    assert all(sha(work/n)==h for n,h in hashes.items())
                for filename in local.rglob('PACKAGE_MANIFEST.json'):
                    if filename.parent.name in ('Complete','Minimal'):
                        verify(filename.parent)
                save(out/'release.json',result)
            capacity=storage_capacity.pilot(work,base)
            from types import SimpleNamespace
            with patch.object(shutil,'disk_usage',return_value=SimpleNamespace(free=capacity['workspace_needed_bytes']-1)):
                low=storage_capacity.pilot(work,base)
                import release_check
                with patch.object(release_check,'REPO',work):
                    assert release_check.run(SimpleNamespace(p10=True,p5_archive_dir=base))==3
                stop,=(work/'status/release_checks').glob('*/release.json')
                assert read(stop)['status']=='LOW_SPACE' and read(stop)['started_jobs']==0
            assert low['status']=='LOW_SPACE' and low['workspace_short_bytes']==1
            result.update(status='PASSED',pilot_capacity=capacity,one_byte_below=low,blocked_batch_started_jobs=read(stop)['started_jobs'])
    except Exception as error:
        result.update(status='FAILED',error=str(error));raise
    finally:save(out/'release.json',result)
    print(out/'release.json',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journey',type=Path,required=True,help='P14 journey/release.json')
    parser.add_argument('--reference-root',type=Path,required=True,help='Unmodified pre-P15 checkout for the comparison')
    args=parser.parse_args()
    run(read(args.journey),args.reference_root.resolve())
