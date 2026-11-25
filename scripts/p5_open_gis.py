"""Read a detached Complete package with the configured QGIS interpreter."""
import json
from pathlib import Path
import sys

from qgis.core import Qgis, QgsApplication, QgsProject


def main(folder):
    app=QgsApplication([],False);app.initQgis()
    project=QgsProject.instance()
    if not project.read(str(folder/'GIS_Project.qgz')):raise ValueError('QGIS could not open the detached project')
    layers=list(project.mapLayers().values())
    invalid=[layer.name() for layer in layers if not layer.isValid()]
    layouts=[layout.name() for layout in project.layoutManager().layouts()]
    if not layers or invalid or not {'Exhibit_EN','Exhibit_CN'}.issubset(layouts):
        raise ValueError(f'Invalid QGIS layers or layouts: {invalid}, {layouts}')
    print(json.dumps(dict(version=Qgis.QGIS_VERSION,layers=len(layers),layouts=sorted(layouts))))
    project.clear()


if __name__=='__main__':main(Path(sys.argv[1]).resolve())
