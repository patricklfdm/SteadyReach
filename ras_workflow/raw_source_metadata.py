"""Read FGDC field definitions only when the entity explicitly names the uploaded table."""
from pathlib import Path
from xml.etree import ElementTree
from .intake_freeze import local

def companion(model, name, column):
    found=[]
    for ref in model.get('attachments',[]):
        if Path(ref['path']).suffix.lower()!='.xml':continue
        path=local(ref)
        if path.stat().st_size>2_000_000:continue
        try:doc=ElementTree.parse(path)
        except ElementTree.ParseError:continue
        for entity in doc.findall('.//detailed'):
            if (entity.findtext('enttyp/enttypl') or '').strip().casefold()!=name.casefold():continue
            for attr in entity.findall('attr'):
                if attr.findtext('attrlabl')!=column:continue
                unit=(attr.findtext('.//attrunit') or '').lower().strip()
                values={}
                if unit in ('meter','meters','metre','metres'):values['unit']='m'
                if unit in ('international foot','international feet'):values['unit']='ft'
                if unit in ('us survey foot','us survey feet'):values['unit']='us_survey_ft'
                vert=(doc.findtext('.//altdatum') or '').upper().strip()
                if vert in ('NORTH AMERICAN VERTICAL DATUM OF 1988','NAVD88'):values['datum']='NAVD88'
                if vert in ('NATIONAL GEODETIC VERTICAL DATUM OF 1929','NGVD29'):values['datum']='NGVD29'
                zone=doc.findtext('.//utmzone')
                south=doc.findtext('.//southbc');north=doc.findtext('.//northbc')
                if (doc.findtext('.//horizdn') or '').upper()=='WGS_1984' and zone and zone.strip().isdigit() and 1<=int(zone)<=60:
                    try:
                        if float(south)>=0:values['crs']='EPSG:'+str(32600+int(zone))
                        elif float(north)<=0:values['crs']='EPSG:'+str(32700+int(zone))
                    except (TypeError,ValueError):pass
                if values:found.append(dict(file=path.name,sha256=ref['sha256'],values=values))
    return found
