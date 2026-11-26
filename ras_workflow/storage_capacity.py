"""Same-volume peak planning for native calculations, archives and a recoverable restore."""
import shutil
from pathlib import Path


def estimate(workspace, archives, *, work_bytes, archive_bytes, restore_bytes):
    for count in (work_bytes, archive_bytes, restore_bytes):
        if type(count) is not int or count < 0:
            raise ValueError('Storage estimates require nonnegative byte counts')
    workspace,archives=Path(workspace).resolve(),Path(archives).resolve()
    same_volume=workspace.stat().st_dev==archives.stat().st_dev
    free=shutil.disk_usage(workspace).free
    archive_free=free if same_volume else shutil.disk_usage(archives).free
    needed=work_bytes+restore_bytes+(archive_bytes if same_volume else 0)
    short=max(0,needed-free)
    archive_short=0 if same_volume else max(0,archive_bytes-archive_free)
    return dict(work_bytes=work_bytes,archive_bytes=archive_bytes,restore_reserve_bytes=restore_bytes,
                same_volume=same_volume,workspace_free_bytes=free,archive_free_bytes=archive_free,
                workspace_needed_bytes=needed,workspace_short_bytes=short,archive_short_bytes=archive_short,
                status='LOW_SPACE' if short or archive_short else 'READY')


# Measured on the 26-job P10 cohort. These figures describe that workload only.
P10_WORKSPACE_PEAK=7147333505
P10_ARCHIVES=39207840+26945486
P10_RESTORE_RESERVE=max(17516982+4096*133,14798504+4096*121)


def pilot(workspace,archives):
    return dict(basis='P10 26-job workstation cohort; peak sample and two verified edition archives',
                sample_sha256='d02d3d647d0166c8f099fbf3b4ed9ae3f7f1d293f3fccd7b5c62c85dd5ba90f0',
                **estimate(workspace,archives,work_bytes=P10_WORKSPACE_PEAK,
                           archive_bytes=P10_ARCHIVES,restore_bytes=P10_RESTORE_RESERVE))
