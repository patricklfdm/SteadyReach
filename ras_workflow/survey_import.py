"""Import a local georeferenced river survey into the editable steady-flow workflow."""
import base64
import hashlib
import json
import re
from pathlib import Path

from pyproj import CRS, Transformer
from rasterio.io import MemoryFile

from .common import ROOT, finite, identifier, intact, item, read, safe_path, save
from .inputs import geometry_errors
from .river import boundary_errors


def fields(obj, allowed, label):
    if not isinstance(obj, dict):
        raise ValueError(f'{label} must be an object')
    unknown = obj.keys() - set(allowed.split())
    if unknown:
        raise ValueError(f'{label}: unsupported fields: ' + ', '.join(sorted(unknown)))


def text(value):
    return isinstance(value, str) and bool(value.strip())


def points(value, minimum=2):
    return (isinstance(value, list) and minimum <= len(value) <= 20000 and
            all(isinstance(p, list) and len(p) == 2 and all(finite(v) for v in p) for p in value))


def validate_model(manifest):
    geom, scenario = manifest['geometry'], manifest['scenario']
    fields(scenario, 'id profiles channel_n overbank_n parameter_source', 'scenario')
    identifier(scenario['id'])
    profiles = scenario['profiles']
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 99:
        raise ValueError('Give 1–99 steady-flow profiles')
    for profile in profiles:
        fields(profile, 'id flow_cfs source', 'profile')
        if not text(profile.get('source')) or not finite(profile.get('flow_cfs')) or profile['flow_cfs'] <= 0:
            raise ValueError('Give each profile a positive discharge and source')
        name = profile.get('id')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _.-]{0,14}', name) or name.endswith(' '):
            raise ValueError('Use distinct ASCII profile names of 1–15 characters')
    if len({p['id'].casefold() for p in profiles}) != len(profiles):
        raise ValueError('Profile names must be distinct')
    if not text(scenario.get('parameter_source')) or not all(finite(scenario.get(k)) and 0 < scenario[k] < 1 for k in ('channel_n','overbank_n')):
        raise ValueError('Give the channel and overbank Manning n and their basis')
    fields(geom, 'schema_version hydraulic_unit horizontal_crs vertical_datum model_type river reach '
           'channel_geometry_basis flow_regime boundaries boundary_slopes cross_sections flowlines structure provenance', 'geometry')
    if geom.get('model_type') != 'river' or geom.get('channel_geometry_basis') not in ('surveyed_channel','combined_survey_and_dem'):
        raise ValueError('The package requires a surveyed river geometry')
    sections = geom['cross_sections']
    if not isinstance(sections, list) or not 4 <= len(sections) <= 500:
        raise ValueError('Give 4–500 cross sections in downstream order')
    lines = geom['flowlines']
    if not isinstance(lines, list) or len(lines) != 1:
        raise ValueError('Give the upstream-to-downstream centerline for one reach')
    line = lines[0]
    fields(line, 'id xy', 'flowline')
    if not text(line.get('id')) or not points(line.get('xy')):
        raise ValueError('Give a flowline identifier and finite projected coordinate pairs')
    for section in sections:
        fields(section, 'rs center_xy cutline_xy station_ft elevation_ft reach_lengths_ft reach_id local_chainage_ft '
               'expansion_contraction reach_length_basis bank_stations_ft manning_segments ineffective_left ineffective_right', 'section')
        if section.get('reach_id',line['id']) != line['id'] or not points(section.get('cutline_xy')) or len(section['cutline_xy']) > 32:
            raise ValueError('Each section needs a cutline of 2–32 vertices in the same reach')
        if not isinstance(section.get('station_ft'), list) or not 3 <= len(section['station_ft']) <= 500:
            raise ValueError('Give 3–500 sampled stations per section')
    fields(geom['boundaries'], 'upstream downstream', 'boundaries')
    for endpoint in geom['boundaries'].values():
        fields(endpoint, 'type stages_ft', 'boundary')
    fields(geom.get('boundary_slopes', {}), 'upstream downstream', 'boundary_slopes')
    if geom.get('provenance') and not (isinstance(geom['provenance'], list) and all(text(s) for s in geom['provenance'])):
        raise ValueError('Geometry source notes must be plain text; attach the source files in the manifest')
    errors = geometry_errors(dict(geom, provenance=geom.get('provenance') or [ref['source'] for ref in manifest['files']])) + boundary_errors(geom, len(profiles))
    if errors:
        raise ValueError('Invalid river survey: ' + '; '.join(errors[:4]))


def parse(files):
    if not isinstance(files, list) or not 3 <= len(files) <= 48:
        raise ValueError('Select survey.json, the surveyed GeoTIFF, and its listed source files')
    data, names = {}, set()
    for entry in files:
        name = entry.get('name') if isinstance(entry, dict) else None
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _.-]{0,119}', name) or name.endswith(('.', ' ')):
            raise ValueError('Survey inputs require plain filenames')
        folded = name.casefold()
        if Path(name).is_reserved() or folded == 'geometry.working.json' or folded in names:
            raise ValueError('Reserved or duplicate survey filename')
        names.add(folded)
        raw = base64.b64decode(entry['content'], validate=True)
        if not raw or len(raw) > 15_000_000:
            raise ValueError('Each survey source must be nonempty and at most 15 MB')
        data[name] = raw
    if sum(map(len,data.values())) > 50_000_000:
        raise ValueError('Survey inputs exceed 50 MB; crop the terrain or reduce the attached sources')
    if 'survey.json' not in data:
        raise ValueError('Include the file named survey.json')
    manifest = json.loads(data['survey.json'].decode('utf-8-sig'))
    fields(manifest, 'schema_version title location terrain files geometry scenario', 'survey.json')
    if manifest.get('schema_version') != 'steadyreach_survey_1':
        raise ValueError('Unsupported survey manifest version')
    try:
        refs = manifest['files']
        if not isinstance(refs, list) or len(refs) != len(data) - 1:
            raise ValueError('Select every listed source exactly once')
        for ref in refs:
            fields(ref, 'name source sha256', 'source file')
        if set(data) - {'survey.json'} != {r['name'] for r in refs}:
            raise ValueError('Select every listed source exactly once')
        for r in refs:
            if not text(r.get('source')) or hashlib.sha256(data[r['name']]).hexdigest() != r.get('sha256'):
                raise ValueError('Source citation or SHA-256 differs: ' + r['name'])
        loc, geom, terrain = manifest['location'], manifest['geometry'], manifest['terrain']
        fields(loc, 'latitude longitude', 'location')
        if not all(finite(loc.get(k)) for k in ('latitude','longitude')) or not -90 < loc['latitude'] < 90 or not -180 < loc['longitude'] < 180:
            raise ValueError('Give the project WGS84 latitude and longitude')
        fields(terrain, 'raster vertical_datum vertical_unit', 'terrain')
        name = terrain['raster']
        if name not in data or not name.lower().endswith(('.tif','.tiff')) or data[name][:4] not in (b'II*\x00', b'MM\x00*', b'II+\x00', b'MM\x00+'):
            raise ValueError('Select the declared survey GeoTIFF')
        if terrain.get('vertical_unit') not in ('m','US survey foot','international foot') or not text(terrain.get('vertical_datum')) or terrain['vertical_datum'] != geom.get('vertical_datum'):
            raise ValueError('Give matching vertical datums and the raster elevation unit')
        definition = geom['horizontal_crs']
        if not isinstance(definition,str) or not re.match(r'^(EPSG:[0-9]+$|PROJ(?:CRS|CS)\[)',definition,re.I):
            raise ValueError('Give a projected EPSG code or projected WKT')
        validate_model(manifest)
        crs = CRS.from_user_input(definition)
        with MemoryFile(data[name]) as source, source.open(driver='GTiff') as raster:
            if raster.driver != 'GTiff' or not crs.is_projected or not crs.equals(raster.crs) or raster.count != 1 or raster.width*raster.height > 16_000_000:
                raise ValueError('Survey terrain must be a single-band projected GeoTIFF in the section CRS, up to 16 million cells')
            x, y = Transformer.from_crs(4326,crs,always_xy=True).transform(loc['longitude'],loc['latitude'])
            locations = [(x,y)] + [s['center_xy'] for s in geom['cross_sections']]
            if not all(raster.bounds.left <= x <= raster.bounds.right and raster.bounds.bottom <= y <= raster.bounds.top for x,y in locations):
                raise ValueError('The site and section centers must lie in the survey raster')
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ValueError('Missing or invalid survey field: ' + str(error)) from error
    return manifest, data


def verified_sources(model):
    entries = [e for e in model.get('attachments', []) if e.get('role') in ('survey_manifest','survey_source')]
    if not entries and model.get('route') != 'survey':
        return []
    manifests = [e for e in entries if e['role'] == 'survey_manifest']
    if len(manifests) != 1:
        raise ValueError('Restore the original survey manifest')
    missing = [Path(e['path']).name for e in entries if not intact([e])]
    if missing:
        raise ValueError('Restore missing or changed survey files: ' + ', '.join(missing))
    path = safe_path(ROOT, manifests[0]['path'])
    declared = {str((path.parent/r['name']).resolve()):r['sha256'] for r in read(path)['files']}
    actual = {str(safe_path(ROOT,e['path'])):e['sha256'] for e in entries if e['role'] == 'survey_source'}
    if actual != declared:
        raise ValueError('Survey source inventory differs from the imported manifest')
    return entries


def parameter_basis(key, config):
    """Show where original values came from without upgrading interpretations to measurements."""
    if key.startswith('c.scenarios.'):
        scenario = config['scenarios'][int(key.split('.')[2])]
        if '.profiles.' in key:
            profile = scenario['profiles'][int(key.split('.')[4])]
            return 'source_input_unverified', profile['source']
        return 'source_input_unverified', scenario.get('parameter_source','')
    if key.startswith('g.cross_sections.'):
        if key.endswith(('.elevation_ft','.station_ft')):
            return 'source_input_unverified', 'Survey-package section profile. Check survey coverage, dates and datum in the attached sources. / 资料包断面剖面，请核对附件中的测量覆盖、日期与基准。'
        if key.endswith(('.bank_stations_ft','.expansion_contraction','.reach_lengths_ft')):
            return 'inferred', 'Hydraulic interpretation in the survey package. Check the bank, length or loss assumption. / 资料包的水力解释，请核对岸站、流程或损失系数。'
    return 'source_input_unverified', 'Imported survey.json and cited originals. Verify applicability to this event. / 见 survey.json 与所列原件，请核对本场适用性。'


def install(folder, config, package):
    manifest, data = package
    dest = folder / 'survey'
    dest.mkdir()
    for name, raw in data.items():
        (dest/name).write_bytes(raw)
    evidence = [item(dest/'survey.json','survey_manifest')]
    for ref in manifest['files']:
        entry = item(dest/ref['name'],'survey_source')
        entry['source'] = ref['source']
        evidence.append(entry)
    save(dest/'geometry.working.json', dict(manifest['geometry'], provenance=evidence))
    terrain = manifest['terrain']
    config.update(geometry='survey/geometry.working.json', scenarios=[manifest['scenario']],
                  terrain=dict(mode='local', raster='survey/'+terrain['raster'], provenance='survey/survey.json',
                               vertical_datum=terrain['vertical_datum'], vertical_unit=terrain['vertical_unit']))
    config['location']['source'] = 'survey/survey.json'
    return evidence


def make_manifest(definition, sources):
    """Write a manifest beside already prepared survey inputs; never overwrite a package."""
    definition = Path(definition).resolve(strict=True)
    folder = definition.parent
    manifest = json.loads(definition.read_text(encoding='utf-8-sig'))
    if definition.name.casefold() == 'survey.json' or 'files' in manifest:
        raise ValueError('Use a separate field definition; the source table is generated')
    manifest['schema_version'] = 'steadyreach_survey_1'
    manifest['files'] = []
    uploads = []
    for filename, citation in sources:
        path = Path(filename).resolve(strict=True)
        if path.parent != folder or path == definition or path.name.casefold() == 'survey.json':
            raise ValueError('Keep each selected source beside the field definition')
        if path.stat().st_size > 15_000_000:
            raise ValueError('Crop the survey to the project reach: ' + path.name)
        raw = path.read_bytes()
        manifest['files'].append(dict(name=path.name,source=citation,sha256=hashlib.sha256(raw).hexdigest()))
        uploads.append(dict(name=path.name,content=base64.b64encode(raw).decode('ascii')))
    raw = json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    parse(uploads + [dict(name='survey.json',content=base64.b64encode(raw).decode('ascii'))])
    dest = folder/'survey.json'
    with dest.open('xb') as output:
        output.write(raw)
    return dest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Create survey.json for the local river survey import')
    parser.add_argument('definition', help='JSON containing location, terrain, geometry and scenario')
    parser.add_argument('--source', nargs=2, action='append', required=True, metavar=('FILE','CITATION'))
    args = parser.parse_args()
    try:
        print(make_manifest(args.definition,args.source))
    except (ValueError,OSError) as exc:
        parser.exit(1, str(exc)+'\n')
