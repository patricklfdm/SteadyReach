"""Standalone native QGIS cartography. Called by the bounded delivery exporter."""
import json, sys, os, math
from pathlib import Path
from qgis.core import *
from qgis.PyQt.QtGui import QColor, QFont, QFontDatabase
from qgis.PyQt.QtCore import QVariant
from osgeo import gdal, ogr, osr


def overview_contour_interval(interval, relief):
    # The 166 mm overview panel can distinguish roughly 100 elevation levels.
    # Align display intervals with the stored contours, including fractional units.
    if relief <= 100 * interval:
        return interval
    target = relief / 100
    magnitude = 10 ** math.floor(math.log10(target))
    nice = next(step * magnitude for step in (1, 2, 5, 10) if step * magnitude >= target)
    return max(1, math.ceil(nice / interval - 1e-9)) * interval


def main(request):
    cfg=json.loads(Path(request).read_text(encoding='utf-8'));out=Path(cfg['output'])
    print('Loading QGIS and terrain',flush=True)
    app=QgsApplication([],False);app.initQgis()
    # Qt's offscreen plugin does not discover Windows system fonts reliably.
    # Register existing local fonts in this process, without installing fonts.
    for font in ['arial.ttf','arialbd.ttf','ariali.ttf','msyh.ttc','msyhbd.ttc']:
        if QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/font))<0:
            raise ValueError('Required exhibit font unavailable: '+font)
    project=QgsProject.instance();project.setCrs(QgsCoordinateReferenceSystem(cfg['crs']))
    project.setFilePathStorage(Qgis.FilePathType.Relative);project.setTitle(cfg['title'])
    gis=out/'GIS';gis.mkdir(exist_ok=True);graph=out/'Graph';graph.mkdir(exist_ok=True)
    layouts=out/'Layouts';layouts.mkdir(exist_ok=True)
    dem=QgsRasterLayer(cfg['dem'],'Ground elevation');assert dem.isValid(),'Invalid DEM'
    stats=dem.dataProvider().bandStatistics(1,QgsRasterBandStats.All)
    lo,hi=stats.minimumValue,stats.maximumValue
    if not hi>lo:raise ValueError('Terrain elevation range is invalid')
    colors=['#365b79','#72a4a0','#d5d9a9','#d1b18c','#8a786b']
    shader=QgsColorRampShader();shader.setColorRampType(QgsColorRampShader.Interpolated)
    shader.setColorRampItemList([QgsColorRampShader.ColorRampItem(lo+(hi-lo)*i/4,QColor(c),f'{lo+(hi-lo)*i/4:.1f}') for i,c in enumerate(colors)])
    raster_shader=QgsRasterShader();raster_shader.setRasterShaderFunction(shader)
    renderer=QgsSingleBandPseudoColorRenderer(dem.dataProvider(),1,raster_shader)
    renderer.setClassificationMin(lo);renderer.setClassificationMax(hi);dem.setRenderer(renderer);project.addMapLayer(dem)
    imagery=None
    if cfg.get('imagery'):
        imagery=QgsRasterLayer(cfg['imagery'],'Offline aerial image');assert imagery.isValid(),'Invalid imagery';project.addMapLayer(imagery)
    # Contours are native GDAL vectors with explicit elevation field and CRS.
    print('Generating full-resolution ground contours',flush=True)
    contours_path=gis/'Contours.shp';driver=ogr.GetDriverByName('ESRI Shapefile');ds=driver.CreateDataSource(str(contours_path))
    sr=osr.SpatialReference();sr.ImportFromWkt(cfg['crs']);layer=ds.CreateLayer('Contours',sr,ogr.wkbLineString)
    layer.CreateField(ogr.FieldDefn('ID',ogr.OFTInteger));layer.CreateField(ogr.FieldDefn('ELEV',ogr.OFTReal))
    source=gdal.Open(cfg['dem']);band=source.GetRasterBand(1);nd=band.GetNoDataValue()
    code=gdal.ContourGenerate(band,float(cfg['contour_interval']),0,[],int(nd is not None),nd or 0,layer,0,1)
    if code:raise ValueError('Native contour generation failed')
    count=layer.GetFeatureCount();layer=None;ds=None;source=None
    contours=QgsVectorLayer(str(contours_path),'Ground contours','ogr');assert contours.isValid()
    interval=float(cfg['contour_interval'])
    overview=overview_contour_interval(interval,hi-lo)
    line=QgsLineSymbol.createSimple({'line_color':'72,64,52,160','line_width':'0.15'})
    cs=QgsPalLayerSettings();cs.fieldName='ELEV';cs.placement=Qgis.LabelPlacement.Line
    if overview > interval:
        metres_per_unit=QgsUnitTypes.fromUnitToUnitFactor(project.crs().mapUnits(),Qgis.DistanceUnit.Meters)
        bounds=cfg['bounds']
        # At close zoom the editable project shows every original contour again.
        detail_scale=(bounds[2]-bounds[0])*metres_per_unit/0.166/2
        detail=f'@map_scale < {detail_scale:.12g}'
        def on_interval(step):
            return f'abs("ELEV" / {step:.12g} - round("ELEV" / {step:.12g})) < 0.000001'
        renderer=QgsRuleBasedRenderer(line)
        rule=renderer.rootRule().children()[0]
        rule.setFilterExpression(f'({detail}) OR ({on_interval(overview)})')
        contours.setRenderer(renderer)
        cs.isExpression=True
        cs.fieldName=f'CASE WHEN ({detail}) OR ({on_interval(5*overview)}) THEN "ELEV" END'
    else:
        contours.renderer().setSymbol(line)
    project.addMapLayer(contours)
    cf=QgsTextFormat();cf.setFont(QFont('Arial'));cf.setSize(6);cf.setColor(QColor('#625342'))
    cb=QgsTextBufferSettings();cb.setEnabled(True);cb.setSize(.4);cb.setColor(QColor(255,255,255,180));cf.setBuffer(cb)
    cs.setFormat(cf);contours.setLabeling(QgsVectorLayerSimpleLabeling(cs));contours.setLabelsEnabled(True)
    model=[];gpkg=gis/'Model_layers.gpkg';sp=cfg['spatial']
    styles={'river':('#0077aa','0.65'),'cross_sections':('#8b2395','0.45'),'structures':('#ff8500','1.0')}
    display={'river':'Model flow path','cross_sections':'Cross sections','banks':'Model bank stations','structures':'Native culvert section'}
    for name,features in sp['layers'].items():
        if name=='structures' and not features:continue
        kind='Point' if name=='banks' else 'LineString';v=QgsVectorLayer(kind,display[name],'memory');v.setCrs(project.crs())
        v.dataProvider().addAttributes([QgsField('name',QVariant.String),QgsField('rs',QVariant.String),QgsField('basis',QVariant.String)])
        v.updateFields()
        for feature in features:
            f=QgsFeature(v.fields());props=feature['properties'];f.setAttributes([props.get('name',''),props.get('rs',''),props.get('basis','')])
            coords=feature['geometry']['coordinates']
            f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(*coords)) if kind=='Point' else QgsGeometry.fromPolylineXY([QgsPointXY(*xy) for xy in coords]))
            assert v.dataProvider().addFeatures([f])[0]
        options=QgsVectorFileWriter.SaveVectorOptions();options.driverName='GPKG';options.layerName=name
        options.actionOnExistingFile=QgsVectorFileWriter.CreateOrOverwriteLayer if gpkg.exists() else QgsVectorFileWriter.CreateOrOverwriteFile
        assert QgsVectorFileWriter.writeAsVectorFormatV3(v,str(gpkg),project.transformContext(),options)[0]==0
        v=QgsVectorLayer(str(gpkg)+'|layername='+name,display[name],'ogr');assert v.isValid()
        if kind=='Point':v.renderer().setSymbol(QgsMarkerSymbol.createSimple({'name':'circle','color':'255,235,70','outline_color':'40,40,40','size':'1.6'}))
        else:
            color,width=styles[name];v.renderer().setSymbol(QgsLineSymbol.createSimple({'line_color':color,'line_width':width}))
        if name=='cross_sections':
            settings=QgsPalLayerSettings();settings.fieldName='rs';settings.placement=Qgis.LabelPlacement.Line
            fmt=QgsTextFormat();fmt.setFont(QFont('Arial'));fmt.setSize(8);fmt.setColor(QColor('#602069'))
            buffer=QgsTextBufferSettings();buffer.setEnabled(True);buffer.setSize(.7);buffer.setColor(QColor('white'));fmt.setBuffer(buffer)
            settings.setFormat(fmt);v.setLabeling(QgsVectorLayerSimpleLabeling(settings));v.setLabelsEnabled(True)
        project.addMapLayer(v);model.insert(0,v)
    root=project.layerTreeRoot();root.setHasCustomLayerOrder(True)
    root.setCustomLayerOrder(model+[contours]+([imagery] if imagery else [])+[dem])
    map_model=QgsLayerTreeModel(root)
    for theme,air in [('Terrain and model',False),('Aerial and model',True)]:
        root.findLayer(dem.id()).setItemVisibilityChecked(not air or imagery is None)
        if imagery:root.findLayer(imagery.id()).setItemVisibilityChecked(air)
        project.mapThemeCollection().insert(theme,QgsMapThemeCollection.createThemeFromCurrentState(root,map_model))
    root.findLayer(dem.id()).setItemVisibilityChecked(True)
    if imagery:root.findLayer(imagery.id()).setItemVisibilityChecked(False)
    bounds=cfg['bounds'];extent=QgsRectangle(*bounds);project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(extent,project.crs()))
    navy=QColor('#183447');gray=QColor('#566975')
    def place(obj,x,y,w,h):obj.attemptMove(QgsLayoutPoint(x,y));obj.attemptResize(QgsLayoutSize(w,h));return obj
    def label(layout,text,x,y,w,h,size=9,bold=False,zh=False,color=navy,bg=None):
        obj=QgsLayoutItemLabel(layout);obj.setText(text);font=QFont('Microsoft YaHei' if zh else 'Arial');font.setPointSizeF(size);font.setBold(bold)
        obj.setFont(font);obj.setFontColor(color);obj.setMargin(0)
        if bg:obj.setBackgroundEnabled(True);obj.setBackgroundColor(QColor(bg))
        layout.addLayoutItem(obj);return place(obj,x,y,w,h)
    exports=[]
    for language in ['EN','CN']:
        zh=language=='CN';layout=QgsPrintLayout(project);layout.initializeDefaults();layout.setName('Exhibit_'+language)
        layout.pageCollection().page(0).setPageSize(QgsLayoutSize(431.8,279.4));layout.renderContext().setDpi(200)
        label(layout,'',0,0,431.8,28,bg='#183447')
        title_font=QFont('Microsoft YaHei' if zh else 'Arial',18,QFont.Bold)
        title_width=QgsLayoutUtils.textWidthMM(title_font,cfg['title'])
        title_size=min(18,18*345/max(1,title_width))
        label(layout,cfg['title'],12,3,350,12,title_size,True,zh,QColor('white'))
        label(layout,('地形、等高线与原生一维模型' if zh else 'TERRAIN, CONTOURS AND NATIVE 1D MODEL')+' | '+cfg['flow_label'],12,17,350,7,9,False,zh,QColor('white'))
        label(layout,cfg['date'],370,5,52,6,9,True,False,QColor('white'))
        label(layout,'条件性 / 待复核' if zh else 'CONDITIONAL / REVIEW',367,17,61,6,8,True,zh,QColor('#ffd3a3'))
        maps=[]
        for i,(x,theme) in enumerate([(28,'Terrain and model'),(238,'Aerial and model')]):
            heading=('地形与等高线' if zh else 'TERRAIN & CONTOURS') if i==0 else ('航片与模型' if zh else 'AERIAL & MODEL')
            if i==1 and not imagery:heading='无可用航片 / 地形视图' if zh else 'IMAGERY UNAVAILABLE / TERRAIN VIEW'
            label(layout,heading,x-16,32,197,7,12,True,zh)
            sub=(f"{cfg['contour_interval']:g} {cfg['vertical_unit_label']} contours" if not zh else f"等高距 {cfg['contour_interval']:g} {cfg['vertical_unit_label']}")
            if overview > interval:
                unit=cfg['vertical_unit_label']
                sub=(f'{overview:g} {unit} contours at this scale; {interval:g} {unit} source interval' if not zh
                     else f'本图等高距 {overview:g} {unit}，原始等高距 {interval:g} {unit}')
            label(layout,sub if i==0 else ('相同范围与模型坐标' if zh else 'Same extent and native geometry'),x-16,41,195,6,9,False,zh)
            m=QgsLayoutItemMap(layout);layout.addLayoutItem(m);place(m,x,50,166,166);m.setCrs(project.crs())
            m.setFollowVisibilityPresetName(theme);m.setFollowVisibilityPreset(True);m.zoomToExtent(extent);m.setFrameEnabled(True)
            m.setFrameStrokeColor(QColor('#9fa9ae'));maps.append(m)
            # The linked bar uses the map CRS unit; never force ftUS on another CRS.
            bar=QgsLayoutItemScaleBar(layout);bar.setLinkedMap(m);bar.setStyle('Single Box');bar.setUnits(project.crs().mapUnits())
            width=extent.width();power=10**math_floor_log10(width/5);segment=max(power,round(width/5/power)*power)
            bar.setUnitsPerSegment(segment);bar.setNumberOfSegments(2);bar.setNumberOfSegmentsLeft(0);bar.setHeight(1.5)
            unit=cfg['horizontal_unit_label']
            bar.setUnitLabel('m' if unit in ('metre','meter') else unit);bar.setFont(QFont('Arial',8));bar.setBackgroundEnabled(True);bar.setBackgroundColor(QColor(255,255,255,225))
            layout.addLayoutItem(bar);place(bar,x+4,204,65,10)
            label(layout,'N',x+150,54,9,5,10,True,bg='white');label(layout,'↑',x+149,58,11,12,22,True,bg='white')
            label(layout,'格网北' if zh else 'Grid N',x+146,72,16,5,7,False,zh,bg='white')
        legend=QgsLayoutItemLegend(layout);legend.setTitle('');legend.setAutoUpdateModel(False);legend.model().rootGroup().removeAllChildren()
        zh_legend={'Model flow path':'河道中心线','Cross sections':'断面线','Model bank stations':'模型岸站',
                   'Native culvert section':'涵洞结构断面','Ground contours':'地形等高线'}
        for layer in model+[contours]:
            node=legend.model().rootGroup().addLayer(layer)
            if zh:
                caption=zh_legend[layer.name()]
                node.setUseLayerName(False);node.setName(caption)
                QgsMapLayerLegendUtils.setLegendNodeUserLabel(node,0,caption)
                legend.model().refreshLayerLegend(node)
        legend.setColumnCount(3);legend.setSplitLayer(True);legend.setSymbolWidth(8);legend.setSymbolHeight(2);legend.setColumnSpace(22)
        legend.setStyleFont(Qgis.LegendComponent.SymbolLabel,QFont('Microsoft YaHei' if zh else 'Arial',9));layout.addLayoutItem(legend);place(legend,20,223,390,20)
        terrain_credit=cfg['terrain_label'];imagery_credit=cfg['imagery_label']
        if zh:
            if terrain_credit=='Reviewed terrain; see Evidence/terrain.json':
                terrain_credit='地形来源见 Evidence/terrain.json'
            imagery_credit=imagery_credit.replace('USGS / USDA NAIP; catalog source years ','USGS / USDA NAIP；影像目录年份 ')
        notes=[
            ('坐标与来源' if zh else 'COORDINATES & SOURCES',cfg['crs_label']+'\n'+cfg['vertical_datum']+'; '+cfg['vertical_unit_label']+'\n'+terrain_credit[:83]),
            ('模型与运行' if zh else 'MODEL & RUN',cfg['flow_label']+'\n'+('运行 ' if zh else 'Run ')+cfg['run_id']+'\n'+(('橙线为计算结构线，非涵孔轮廓。' if zh else 'Orange line: computational structure, not barrel footprint.') if sp['layers'].get('structures') else ('纯河道，未建桥梁结构。' if zh else 'River reach; bridge structures excluded.'))),
            ('复核与限制' if zh else 'REVIEW & LIMITS',('水力 QA 待复核；条件性输入须核实。\n地面等高线不代表水位或洪泛边界。\n' if zh else 'Hydraulic QA remains open; conditional inputs.\nGround contours are not water levels or flood limits.\n')+imagery_credit[:80])]
        for x,(heading,body) in zip([12,151,290],notes):
            label(layout,heading,x,249,130,5,9,True,zh);label(layout,body,x,255,130,17,7.5,False,zh)
        footer='QGIS 打印布局 | 17 × 11 英寸 | 等高距不代表测量精度。' if zh else 'QGIS native Print Layout | 17 x 11 in | Contour interval is not survey accuracy.'
        label(layout,footer,12,273,406,4,7.5,False,zh,color=gray)
        assert project.layoutManager().addLayout(layout)
        template=layouts/('Exhibit_'+language+'.qpt');context=QgsReadWriteContext();context.setPathResolver(QgsPathResolver(str(template)))
        assert layout.saveAsTemplate(str(template),context)
        exports.append(dict(language=language,layout=layout.name(),scales=[m.scale() for m in maps]))
    project_path=out/'GIS_Project.qgz';assert project.write(str(project_path));project.clear();assert project.read(str(project_path))
    assert all(l.isValid() for l in project.mapLayers().values())
    for e in exports:
        exporter=QgsLayoutExporter(project.layoutManager().layoutByName(e['layout']))
        pdf=graph/('Exhibit_'+e['language']+'.pdf');settings=QgsLayoutExporter.PdfExportSettings();settings.dpi=200
        print(f'Exporting {pdf.name}',flush=True)
        assert exporter.exportToPdf(str(pdf),settings)==QgsLayoutExporter.Success
        png=graph/('Exhibit_'+e['language']+'.png');settings2=QgsLayoutExporter.ImageExportSettings();settings2.dpi=120
        print(f'Exporting {png.name}',flush=True)
        assert exporter.exportToImage(str(png),settings2)==QgsLayoutExporter.Success
    receipt=dict(status='EXPORTED_PENDING_VISUAL_REVIEW',qgis_version=Qgis.QGIS_VERSION,contour_features=count,
        source_contour_interval=interval,overview_contour_interval=overview,
        exports=exports,layers=len(project.mapLayers()),saved_project_reopened=True,crs=project.crs().authid())
    (out/'Evidence/qgis_export.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    project.clear();app.exitQgis()


def math_floor_log10(value):
    import math
    if value<=0:raise ValueError('Invalid map width')
    return math.floor(math.log10(value))


if __name__=='__main__':main(sys.argv[1])
