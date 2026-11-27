"""Create location-specific survey requests tied to one calculated river edition."""
import base64
import csv
import io
import json
from datetime import date
from zipfile import ZipFile, ZIP_DEFLATED

from pyproj import CRS, Transformer

from . import field_return
from .common import ROOT, digest, intact, read, save
from .revision_inputs import station_key

EXTRA = ('request_id', 'survey_date', 'method', 'uncertainty_ft')
TOPICS = {
    'tie': ('Recover gage zero, bridge face and flood-mark benchmark ties and times.',
            '查水尺零点、桥侧与洪痕的水准联测原件和记录时间。'),
    'profile': ('Recover bed-to-floodplain transects, openings and crest levels along this flow path.',
                '查该过流路径从水下河床到漫滩的剖面、路堤开口及堤顶高程。'),
    'stage': ('Seek independent event water levels between controls, with time and discharge.',
              '查控制点之间的独立水位、观测时间及同期流量。'),
}


def dates(first, last):
    try:
        start, end = date.fromisoformat(first), date.fromisoformat(last)
    except (ValueError, TypeError) as exc:
        raise ValueError('Choose the first and last applicable survey dates / 请填写可用测量起止日期') from exc
    if end < start:
        raise ValueError('End date precedes start / 截止日期早于开始日期')
    return start.isoformat(), end.isoformat()


def locations(geometry, diagnostic, extra):
    sections = geometry['cross_sections']
    ids = [station_key(r['rs']) for r in sections]
    where = {}
    def include(rs, topic, basis):
        key = (station_key(rs), topic)
        if key[0] not in ids:
            raise ValueError('Unknown section / 断面不存在 RS '+key[0])
        where.setdefault(key, [])
        if basis not in where[key]:
            where[key].append(basis)
    for result in diagnostic.get('comparisons', []):
        if result.get('status') != 'DIAGNOSTIC_REVIEW':
            continue
        for point in result['checks']:
            include(point['rs'], 'tie', point['source'])
        if result['id'] in ('spacing', 'bed', 'terrain'):
            worst = result['max_change']
            include(worst['rs'], 'profile', f"{result['id']} · Δ {worst['delta_ft']:+.3f} ft")
    middle = min(range(1, len(ids)-1), key=lambda i: abs(float(ids[i])-(float(ids[0])+float(ids[-1]))/2))
    include(ids[middle], 'stage', 'Interior search area / 河段内部资料搜索范围')
    for rs in extra:
        include(rs, 'profile', 'Additional field transect / 补充测线')
    if not any(topic == 'profile' for _, topic in where):
        include(ids[middle], 'profile', 'Bed and floodplain survey / 河床与漫滩调查')
    return where


def issue(key, body):
    model, summary, geometry, fields = field_return.context(key, body)
    if geometry.get('model_type') != 'river':
        raise ValueError('Choose a river reach / 请选择河道项目')
    ref = model.get('latest_factor_diagnostic')
    diagnostic = {}
    if ref and intact([ref]):
        candidate = read(ROOT/ref['path'])
        if candidate.get('baseline') == model['summary']:
            diagnostic = candidate
    start, end = dates(body.get('start',''), body.get('end',''))
    extra = [r.strip() for r in str(body.get('stations','')).split(',') if r.strip()]
    if len(extra) > 100:
        raise ValueError('Use up to 100 section identifiers / 最多 100 个断面')
    crs = CRS.from_user_input(geometry['horizontal_crs'])
    if not crs.is_projected:
        raise ValueError('Locate the sections in a projected CRS first / 请先完成断面地理定位')
    transformer = Transformer.from_crs(crs, 4326, always_xy=True)
    def point(xy):
        return list(transformer.transform(*xy, errcheck=True))
    sections = {station_key(r['rs']):(i,r) for i,r in enumerate(geometry['cross_sections'])}
    features = []
    selected = {}
    for (rs, topic), reasons in locations(geometry, diagnostic, extra).items():
        i, row = sections[rs]
        field = f'g.cross_sections.{i}.elevation_ft' if topic == 'profile' else None
        if field:
            selected[field] = fields[field]
        shape = (dict(type='LineString', coordinates=[point(p) for p in row['cutline_xy']]) if field
                 else dict(type='Point', coordinates=point(row['center_xy'])))
        features.append(dict(type='Feature', geometry=shape, properties=dict(rs=rs, topic=topic,
            task_en=TOPICS[topic][0], task_zh=TOPICS[topic][1], model_field=field, reasons=reasons,
            datum=geometry['vertical_datum'], start=start, end=end)))
    manifest = dict(project=key, title=model['title'], summary=model['summary'], run_id=summary['hydraulics']['run_id'],
                    profiles=[dict(profile=p['profile_id'],flow_cfs=p['flow_cfs']) for p in summary['hydraulics']['profiles']],
                    datum=geometry['vertical_datum'], start=start, end=end,
                    diagnostic=ref if diagnostic else None, fields=list(selected), features=features)
    request_id = digest(manifest)
    file = field_return.core.folder(key)/'field_requests'/request_id/'manifest.json'
    if file.exists() and read(file) != manifest:
        raise ValueError('Survey request record changed / 补测单记录已改变')
    save(file,manifest)
    csv_in = csv.DictReader(io.StringIO(field_return.worksheet(model,geometry,selected)))
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf,fieldnames=(*field_return.COLUMNS,*EXTRA))
    writer.writeheader()
    writer.writerows(dict(r,request_id=request_id) for r in csv_in)
    zipbuf = io.BytesIO()
    with ZipFile(zipbuf,'w',ZIP_DEFLATED) as archive:
        archive.writestr('Survey_locations.geojson',json.dumps(dict(type='FeatureCollection',features=features),ensure_ascii=False))
        archive.writestr('Field_values.csv',buf.getvalue().encode('utf-8-sig'))
        archive.writestr('Manifest.json',json.dumps(manifest,indent=2,ensure_ascii=False))
        archive.writestr('Read_me.txt',(
            f"{model['title']} | {start} — {end} | {geometry['vertical_datum']}\n"
            "Seek dated historical records first. Map points are search locations; record actual observation coordinates, bridge side and time. "
            "Return the original record, units, datum realization, control, method and uncertainty. "
            "For geometry fill Field_values.csv at the listed stations and use Import a field return. "
            "For stages use the original measurement import with actual coordinates. Retain contemporary surveys separately.\n"
            "优先查事件期原件。地图点为调查位置，请记录实测坐标、桥侧和时间。提供原件、单位、高程基准、水准控制、方法及精度。"
            "几何按所列站距填写 Field_values.csv，再从补测回传导入。水位通过原始测量表入口按实际坐标导入。当代测量另存。\n"
        ).encode('utf-8-sig'))
    return dict(request_id=request_id, count=len(features), file='Field_request_'+request_id[:10]+'.zip',
                content=base64.b64encode(zipbuf.getvalue()).decode('ascii'))


def evidence(key, content, summary_hash):
    """Verify the packet for every returned geometry value, while accepting legacy worksheets."""
    reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
    if tuple(reader.fieldnames or ()) == field_return.COLUMNS:
        return content, {}
    if tuple(reader.fieldnames or ()) != (*field_return.COLUMNS,*EXTRA):
        raise ValueError('Use the downloaded field worksheet / 请使用本版导出的补测表')
    result = io.StringIO(newline='')
    writer = csv.DictWriter(result,fieldnames=field_return.COLUMNS)
    writer.writeheader()
    details = {}
    manifests = {}
    for row in reader:
        if None in row or None in row.values():
            raise ValueError('Malformed survey return row / 补测表列数有误')
        request = row['request_id']
        if len(request)!=64 or any(c not in '0123456789abcdef' for c in request):
            raise ValueError('Invalid field request ID / 补测单编号无效')
        if request not in manifests:
            path = field_return.core.folder(key)/'field_requests'/request/'manifest.json'
            if not path.is_file():
                raise ValueError('Restore the original survey request / 请恢复对应的补测单')
            manifest = read(path)
            if digest(manifest)!=request or manifest['summary']['sha256']!=summary_hash:
                raise ValueError('Survey request is for a different edition / 补测单属于其他版本')
            manifests[request] = manifest
        manifest=manifests[request]
        if row['field'] not in manifest['fields']:
            raise ValueError('Field was not requested / 该断面不在补测单内')
        if row['value'].strip():
            try:
                day=date.fromisoformat(row['survey_date']).isoformat()
                uncertainty=float(row['uncertainty_ft']) if row['uncertainty_ft'].strip() else None
            except (ValueError,TypeError) as e:
                raise ValueError('Check survey date and uncertainty in ft / 请检查实测日期及精度（ft）') from e
            if not manifest['start'] <= day <= manifest['end']:
                raise ValueError('Outside the historical window. Preserve the survey for a separately dated edition. / 测量超出历史时段，请用于另立的对应年代版本。')
            if not row['method'].strip() or (uncertainty is not None and not (0 < uncertainty < float('inf'))):
                raise ValueError('Supply a method and positive uncertainty, or leave unknown accuracy blank / 请填方法，精度未知时留空')
            details[row['field']]=dict(date=day,method=row['method'].strip(),uncertainty_ft=uncertainty,request_id=request)
        writer.writerow({k:row[k] for k in field_return.COLUMNS})
    return result.getvalue(),details
