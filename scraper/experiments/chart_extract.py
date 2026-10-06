"""Udtraek af renteprognose-serier fra Jyske Banks Renteprognose-PDF'er.

UVERIFICERET - se README.md i denne mappe. Brug ikke tallene i datasættet,
foer de er efterproevet mod en uafhaengig kilde.
"""
"""Udtraek af renteprognose-serier fra Jyske Banks Renteprognose-PDF'er.

Graferne er vektorgrafik: tal og kurver ligger som koordinater, saa vaerdierne
kan laeses praecist uden OCR. Hver side har op til to grafer; hver graf har en
gitterkasse hvis vandrette linjer ligger praecis paa y-aksetallene.
"""
import pdfplumber, re
from collections import defaultdict

NAVN={"jan":1,"feb":2,"mar":3,"apr":4,"maj":5,"jun":6,"jul":7,"aug":8,"sep":9,"okt":10,"nov":11,"dec":12}

def _grid_boxes(page):
    horiz=[l for l in page.lines
           if abs(l["top"]-l["bottom"])<1.5 and (l["x1"]-l["x0"])>80
           and (l.get("linewidth") or 0)<1.0]
    groups=defaultdict(list)
    for l in horiz:
        groups[(round(l["x0"]), round(l["x1"]))].append(l)
    boxes=[]
    for (x0,x1),ls in groups.items():
        tops=sorted({round(l["top"],2) for l in ls})
        if len(tops)<3: continue
        boxes.append({"x0":x0,"x1":x1,"grid":tops})
    boxes.sort(key=lambda b: min(b["grid"]))
    return boxes

def _y_calib(page, box):
    nums=[(w["top"], float(w["text"].replace(",",".")))
          for w in page.extract_words()
          if re.match(r"^-?\d+,\d+$", w["text"]) and w["x1"] < box["x0"]+6]
    pairs=[]
    for gt in box["grid"]:
        cand=[(abs(nt-gt), val) for nt,val in nums if abs(nt-gt)<12]
        if cand:
            cand.sort()
            # undgaa at samme aksetal bruges til to gitterlinjer
            pairs.append((gt, cand[0][1]))
    # regression: vaerdi = a*top + b
    if len(pairs)<3: return None
    n=len(pairs); sx=sum(t for t,_ in pairs); sy=sum(v for _,v in pairs)
    sxx=sum(t*t for t,_ in pairs); sxy=sum(t*v for t,v in pairs)
    den=n*sxx-sx*sx
    if abs(den)<1e-9: return None
    a=(n*sxy-sx*sy)/den; b=(sy-a*sx)/n
    # sanity: stigende top skal give faldende vaerdi
    if a>0: return None
    return {"a":a,"b":b,"n":len(pairs),
            "vtop":a*min(box["grid"])+b,"vbot":a*max(box["grid"])+b}

def analyse(path):
    out=[]
    with pdfplumber.open(path) as d:
        for pno,page in enumerate(d.pages,1):
            for bi,box in enumerate(_grid_boxes(page)):
                cal=_y_calib(page,box)
                if not cal: continue
                # kurver inde i kassen
                inside=defaultdict(list)
                for c in page.curves:
                    pts=c.get("pts",[])
                    if not pts: continue
                    sel=[(p[0],p[1]) for p in pts
                         if box["x0"]-2<=p[0]<=box["x1"]+2
                         and min(box["grid"])-2<=p[1]<=max(box["grid"])+2]
                    if len(sel)<5: continue
                    inside[(c.get("stroking_color"), round(c.get("linewidth") or 0,2))] += sel
                out.append({"side":pno,"box":bi,"x0":box["x0"],"x1":box["x1"],
                            "cal":cal,"serier":dict(inside)})
    return out

if __name__=="__main__":
    import sys
    for r in analyse(sys.argv[1]):
        c=r["cal"]
        print(f"side {r['side']} graf {r['box']}: x {r['x0']}..{r['x1']}  "
              f"y-akse {c['vbot']:.2f}..{c['vtop']:.2f} ({c['n']} aksetal)  "
              f"{len(r['serier'])} serier")

def _x_calib(page, box):
    """Kalibrer x: maaned = a*x + b, ud fra datoetiketter under grafen."""
    tops=[t for t in page.lines
          if abs(t["top"]-t["bottom"])<1.5 and round(t["x0"])==box["x0"]]
    gtops=[round(t["top"],1) for t in tops]
    if not gtops: return None
    ybot=max(gtops)
    dts=[]
    for w in page.extract_words():
        m=re.match(r"^([a-zæøå]{3})-(\d{2})$", w["text"].lower())
        if m and ybot < w["top"] < ybot+26 and box["x0"]-14 < w["x0"] < box["x1"]+6:
            # datoetiketterne er CENTREREDE om deres position
            dts.append(((w["x0"]+w["x1"])/2, int(m.group(2))*12 + NAVN.get(m.group(1),1) - 1))
    if len(dts)<3: return None
    dts.sort()
    n=len(dts); sx=sum(x for x,_ in dts); sy=sum(v for _,v in dts)
    sxx=sum(x*x for x,_ in dts); sxy=sum(x*v for x,v in dts)
    den=n*sxx-sx*sx
    if abs(den)<1e-9: return None
    return {"a":(n*sxy-sx*sy)/den, "b":(sy-((n*sxy-sx*sy)/den)*sx)/n, "n":len(dts)}

def main_series(page, box, min_frac=0.5):
    """Den dominerende serie i kassen = bankens egen prognose."""
    inside=defaultdict(list)
    for c in page.curves:
        pts=c.get("pts",[])
        if not pts: continue
        sel=[(p[0],p[1]) for p in pts
             if box["x0"]-2<=p[0]<=box["x1"]+2
             and min(box["grid"])-2<=p[1]<=max(box["grid"])+2]
        if len(sel)>=5:
            inside[(c.get("stroking_color"), round(c.get("linewidth") or 0,2))] += sel
    if not inside: return None
    wid=box["x1"]-box["x0"]
    best=None
    for key,pts in inside.items():
        pts=sorted(pts)
        span=pts[-1][0]-pts[0][0]
        if span < min_frac*wid: continue
        if best is None or len(pts)>len(best[1]): best=(key,pts)
    return best

def forecast_series(path):
    """Returner [(fil, side, aksestart, akseslut, [(maaned, vaerdi), ...])]."""
    out=[]
    import pdfplumber as _p
    with _p.open(path) as d:
        for pno,page in enumerate(d.pages,1):
            for bi,box in enumerate(_grid_boxes(page)):
                yc=_y_calib(page,box)
                if not yc: continue
                xc=_x_calib(page,box)
                if not xc: continue
                ms=main_series(page,box)
                if not ms: continue
                key,pts=ms
                pts=sorted(pts)
                ser=[]
                for x,y in pts:
                    mon=xc["a"]*x+xc["b"]
                    ser.append((mon, yc["a"]*y+yc["b"]))
                out.append({"side":pno,"box":bi,"x0":box["x0"],"x1":box["x1"],
                            "ycal":yc,"xcal":xc,"key":key,"serie":ser})
    return out
