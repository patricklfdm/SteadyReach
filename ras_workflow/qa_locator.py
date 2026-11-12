"""A location aid from native GIS cutlines; never an inundation map."""
import h5py
from .common import ROOT,item

def draw(hyd,folder,issues):
    from .report_data import plot_style
    with h5py.File(ROOT/hyd['raw_hdf']['path']) as f:
        base=f['Geometry/Cross Sections']
        if any(k not in base for k in ['Polyline Info','Polyline Points','Attributes']):return None
        info=base['Polyline Info'][:];points=base['Polyline Points'][:];attrs=base['Attributes'][:]
        if len(info)!=len(attrs) or not len(points):return None
        plt=plot_style();fig,ax=plt.subplots(figsize=(8,5));marked={str(i['station']) for i in issues if i.get('station') is not None}
        for row,a in zip(info,attrs):
            start,count=row[:2];line=points[start:start+count]
            if len(line)<2:continue
            rs=a['RS'].decode().strip();hit=rs in marked
            ax.plot(line[:,0],line[:,1],color='#b84c36' if hit else '#245477',lw=2 if hit else 1)
            ax.annotate('RS '+rs,line[len(line)//2],xytext=(4,5),textcoords='offset points',fontsize=8)
        ax.set_aspect('equal',adjustable='datalim');ax.set_xlabel('Native GIS X (source coordinate units)');ax.set_ylabel('Native GIS Y (source coordinate units)')
        ax.set_title('Model section locations / red = a located QA finding\nCRS not inferred; not an inundation map',fontsize=10);ax.grid(alpha=.2);fig.tight_layout()
        path=folder/'section_locator.png';fig.savefig(path,dpi=150);plt.close(fig)
    return item(path,'native_section_location_aid')
