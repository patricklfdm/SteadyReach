"""Siletz benchmark discharge, with portable raw V1 pages and archived RDB support."""
import csv
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from zoneinfo import ZoneInfo

from ras_workflow.common import utc
from ras_workflow.source_fetch import Download
from ras_workflow.usgs_water import pages, query

V1_NAME = 'USGS_discharge_v1.zip'
LEGACY_NAME = 'discharge.rdb'
URL = query('continuous', monitoring_location_id='USGS-14305500', parameter_code='00060',
            datetime='2017-11-01T07:00:00Z/2018-03-02T08:00:00Z', limit=1000)


def obtain(folder):
    destination = folder / V1_NAME
    client = Download(limit=60_000_000, timeout=45)
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        archive = Path(tmp) / V1_NAME
        records = []
        with ZipFile(archive, 'w', compression=ZIP_DEFLATED) as z:
            for i, (address, raw, _) in enumerate(pages(URL, client.get), 1):
                name = f'page_{i:03d}.json'
                z.writestr(name, raw)
                records.append(dict(url=address, name=name, sha256=hashlib.sha256(raw).hexdigest()))
            z.writestr('manifest.json', json.dumps(dict(query=URL, retrieved_utc=utc(), pages=records)))
        read_v1(archive)
        archive.rename(destination)
    return destination


def read_v1(path):
    result = {}
    pacific = ZoneInfo('America/Los_Angeles')
    with ZipFile(path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        rows = manifest['pages']
        if manifest['query'] != URL or not 1 <= len(rows) <= 150:
            raise ValueError('Unexpected USGS discharge query or page count')
        index = 0
        def fetch(address):
            nonlocal index
            if index >= len(rows) or rows[index]['url'] != address:
                raise ValueError('Missing or reordered USGS discharge pages')
            row = rows[index]
            index += 1
            info = archive.getinfo(row['name'])
            if info.file_size > 2_000_000:
                raise ValueError('Unexpected USGS discharge page size')
            raw = archive.read(info)
            if hashlib.sha256(raw).hexdigest() != row['sha256']:
                raise ValueError('USGS discharge page fingerprint changed')
            return raw
        for _, _, data in pages(URL, fetch):
            for feature in data['features']:
                p = feature['properties']
                if (p['monitoring_location_id'],p['parameter_code'],p['unit_of_measure']) != ('USGS-14305500','00060','ft^3/s'):
                    raise ValueError('USGS discharge station, parameter or unit mismatch')
                if p['approval_status'] != 'Approved' or p['value'] is None:
                    continue
                stamp = datetime.fromisoformat(p['time'])
                if stamp.utcoffset() is None:
                    raise ValueError('Discharge timestamp lacks a UTC offset')
                local = stamp.astimezone(pacific)
                if local.utcoffset() != timedelta(hours=-8):
                    continue  # Frozen event protocol uses Pacific standard time.
                key = local.replace(tzinfo=None)
                value = float(p['value'])
                if key in result or not math.isfinite(value):
                    raise ValueError('Duplicate time series or nonfinite USGS discharge')
                result[key] = value
        if index != len(rows) or not result:
            raise ValueError('Unexpected additional pages or no approved standard-time discharges')
    return result


def archived_input(folder):
    for name in (V1_NAME, LEGACY_NAME):
        if (folder/name).is_file():
            return folder/name
    return None


def read_discharge(path):
    if path.name == V1_NAME:
        return read_v1(path)
    with path.open(encoding='utf-8-sig') as handle:
        reader=csv.DictReader((s for s in handle if not s.startswith('#')),delimiter='\t')
        return {datetime.fromisoformat(r['datetime']):float(r['117415_00060']) for r in reader
                if r['site_no']=='14305500' and r['tz_cd']=='PST' and r['117415_00060_cd']=='A'}
