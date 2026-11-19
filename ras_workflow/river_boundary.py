"""Use independently supported longer exterior terrain trends when local intervals reverse."""
from itertools import combinations
from statistics import median


def trend(sections,side,bed,distance):
    trials=[]
    for n in (5,7,9):
        if n>(len(sections)+1)//2:
            continue
        rows=sections[:n] if side=='upstream' else sections[-n:]
        heights=[bed(r) for r in rows]
        if None in heights:
            continue
        chain=[0.]
        for a,b in zip(rows,rows[1:]):
            chain.append(chain[-1]+distance(a['center_xy'],b['center_xy']))
        if any(b<=a for a,b in zip(chain,chain[1:])):
            continue
        slopes=[(heights[i]-heights[j])/(chain[j]-chain[i]) for i,j in combinations(range(n),2)]
        slope=median(slopes)
        fall=heights[0]-heights[-1]
        # A local numerical screen. A repeatable surface-bed trend is still an
        # assumption for the water-surface energy gradient, especially at backwater.
        supported=(fall>=.5 and round(slope,6)>0 and sum(v>0 for v in slopes)>=.7*len(slopes))
        trials.append(dict(rs=[r['rs'] for r in rows],length_ft=chain[-1],net_fall_ft=fall,
                           median_pairwise_slope=slope,supported=supported))
    estimates=[r['median_pairwise_slope'] for r in trials if r['supported']]
    if len(estimates)<2:
        return None
    return dict(slope=round(median(estimates),6),range=[round(min(estimates),6),round(max(estimates),6)],
                method='Median of pairwise DEM bed slopes over nested exterior windows',windows=trials,
                limitations='Overlapping windows share samples. Unmeasured bed, tidal or bridge backwater and stage controls require independent evidence.')
