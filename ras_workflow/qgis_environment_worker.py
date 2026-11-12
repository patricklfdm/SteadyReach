"""Standalone QGIS Python process for software-only export/reopen validation."""
import json
import sys
from pathlib import Path


def main():
    from qgis.core import (Qgis,QgsApplication,QgsProject,QgsVectorLayer,QgsFeature,QgsGeometry,
        QgsPrintLayout,QgsLayoutItemMap,QgsLayoutPoint,QgsLayoutSize,QgsLayoutExporter)
    folder=Path(sys.argv[1]).resolve()
    app=QgsApplication([],False);app.initQgis()
    project=QgsProject.instance()
    layer=QgsVectorLayer('Point?crs=EPSG:4326','Software probe — no site data','memory')
    if not layer.isValid():raise RuntimeError('QGIS vector provider failed')
    feature=QgsFeature();feature.setGeometry(QgsGeometry.fromWkt('POINT (0 0)'))
    ok,_=layer.dataProvider().addFeatures([feature])
    if not ok:raise RuntimeError('QGIS feature write failed')
    layer.updateExtents();project.addMapLayer(layer)
    layout=QgsPrintLayout(project);layout.initializeDefaults();layout.setName('Software environment check')
    project.layoutManager().addLayout(layout)
    view=QgsLayoutItemMap(layout);layout.addLayoutItem(view)
    view.attemptMove(QgsLayoutPoint(20,20));view.attemptResize(QgsLayoutSize(160,100))
    view.setLayers([layer]);extent=layer.extent();extent.grow(0.01);view.zoomToExtent(extent)
    code=QgsLayoutExporter(layout).exportToPdf(str(folder/'environment_qgis.pdf'),QgsLayoutExporter.PdfExportSettings())
    if code!=QgsLayoutExporter.Success:raise RuntimeError('QGIS PDF export failed: '+str(code))
    if not project.write(str(folder/'environment.qgz')):raise RuntimeError('QGIS project save failed')
    project.clear()
    if not project.read(str(folder/'environment.qgz')):raise RuntimeError('QGIS project reopen failed')
    if not project.layoutManager().layoutByName('Software environment check'):raise RuntimeError('Saved layout is missing')
    (folder/'qgis_probe.json').write_text(json.dumps({'status':'PASSED','version':Qgis.QGIS_VERSION,
        'scope':'QGIS import, vector provider, PDF export, project save/reopen; no site data'}),encoding='utf-8')
    project.clear()
    # Process exit owns this isolated Qt/QGIS application; no user windows are closed.
    return 0


if __name__=='__main__':raise SystemExit(main())
