from __future__ import annotations

import csv, io, math, re, shutil, time, urllib.parse, zipfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

USER_AGENT = "BarcharRace-photo-pack/2.2 (https://github.com/ramses23/BarcharRace; BarChartStudio asset preparation)"
MAX_BYTES = 130 * 1024
TARGET = 512
ROOT = Path("photo_pack_batch03")
ZIP_PATH = Path("football_player_photos_batch03_png_max130kb.zip")

PLAYERS = [
    {"player":"Adolfo Baloncieri","file":"adolfo_baloncierri.png","titles":["Adolfo Baloncieri"]},
    {"player":"Amílcar Barbuy","file":"am_lcar_barbuy.png","titles":["Amílcar Barbuy"]},
    {"player":"Carlos Izaguirre","file":"carlos_izaguirre.png","titles":["Carlos Izaguirre (footballer)","Carlos Izaguirre"]},
    {"player":"Guillermo Stábile","file":"guillermo_st_bile.png","titles":["Guillermo Stábile"]},
    {"player":"Haroldo Domingues","file":"haroldo_domingues.png","titles":["Haroldo Domingues"]},
    {"player":"Jair da Rosa Pinto","file":"jair.png","titles":["Jair da Rosa Pinto"]},
    {"player":"Jon Dahl Tomasson","file":"jon_dahl_tomasson.png","titles":["Jon Dahl Tomasson"]},
    {"player":"José Tognola","file":"jose_tognola.png","titles":["José Tognola","Jose Tognola"]},
    {"player":"Manuel Ferreira","file":"manuel_ferreira.png","titles":["Manuel Ferreira (footballer)","Manuel Ferreira"]},
    {"player":"Ángel Romano","file":"ngel_romano.png","titles":["Ángel Romano"]},
    {"player":"Raúl González","file":"ra_l.png","titles":["Raúl (footballer)","Raúl González"]},
    {"player":"Telésforo Báez","file":"tel_sforo_b_ez.png","titles":["Telésforo Báez","Telesforo Báez"]},
    {"player":"Alberto Marcovecchio","file":"alberto_marcovecchio.png","titles":["Alberto Marcovecchio"]},
    {"player":"Carlos Pavón","file":"carlos_pav_n.png","titles":["Carlos Pavón"]},
    {"player":"David Arellano","file":"david_arellano.png","titles":["David Arellano"]},
    {"player":"Didi","file":"didi.png","titles":["Didi (footballer, born 1928)","Didi"]},
    {"player":"Eusébio","file":"eus_bio.png","titles":["Eusébio"]},
    {"player":"Gerardo Rivas","file":"gerardo_rivas.png","titles":["Gerardo Rivas"]},
    {"player":"Gyula Zsengellér","file":"gyula_zsengell_r.png","titles":["Gyula Zsengellér"]},
    {"player":"Ildefonso López","file":"ildefonso_l_pez.png","titles":["Ildefonso López","Ildefonso Lopez footballer"]},
]

S = requests.Session(); S.headers.update({"User-Agent": USER_AGENT})

def get_json(url, params=None, attempts=4):
    last=None
    for i in range(attempts):
        try:
            r=S.get(url, params=params, timeout=60); r.raise_for_status(); return r.json()
        except Exception as e:
            last=e; time.sleep(min(2**i,8))
    raise RuntimeError(f"request failed {url}: {last}")

def download(url):
    r=S.get(url,timeout=120); r.raise_for_status(); return r.content

def commons_info(file_name):
    data=get_json("https://commons.wikimedia.org/w/api.php",{"action":"query","format":"json","prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1400,"titles":"File:"+file_name})
    page=next(iter(data["query"]["pages"].values())); infos=page.get("imageinfo",[])
    if not infos: raise RuntimeError("no imageinfo")
    info=infos[0]; ext=info.get("extmetadata",{})
    return {"file_name":file_name,"page_url":"https://commons.wikimedia.org/wiki/"+urllib.parse.quote(("File:"+file_name).replace(" ","_"),safe=":()_,-."),"image_url":info.get("thumburl") or info.get("url"),"license":ext.get("LicenseShortName",{}).get("value","") ,"artist":ext.get("Artist",{}).get("value","")}

def via_wikipedia(title):
    data=get_json("https://en.wikipedia.org/w/api.php",{"action":"query","format":"json","redirects":1,"prop":"pageprops|pageimages","piprop":"thumbnail|name","pithumbsize":1400,"titles":title})
    page=next(iter(data["query"]["pages"].values()))
    qid=page.get("pageprops",{}).get("wikibase_item")
    if qid:
        wd=get_json(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
        claims=wd["entities"][qid].get("claims",{}).get("P18",[])
        if claims:
            fn=claims[0]["mainsnak"]["datavalue"]["value"]; x=commons_info(fn); x["method"]="Wikidata P18"; x["qid"]=qid; return x
    fn=page.get("pageimage")
    if fn:
        x=commons_info(fn); x["method"]="Wikipedia pageimage"; x["qid"]=qid or ""; return x
    return None

def commons_search(query):
    data=get_json("https://commons.wikimedia.org/w/api.php",{"action":"query","format":"json","generator":"search","gsrsearch":query+" footballer","gsrnamespace":6,"gsrlimit":10,"prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1400})
    pages=data.get("query",{}).get("pages",{})
    # rank filenames containing surname/full name
    tokens=[t.lower() for t in re.findall(r"[A-Za-zÀ-ÿ]+",query) if len(t)>2]
    candidates=[]
    for p in pages.values():
        title=p.get("title",""); score=sum(t in title.lower() for t in tokens)
        ii=p.get("imageinfo",[])
        if not ii: continue
        info=ii[0]; ext=info.get("extmetadata",{}); candidates.append((score,title,info,ext))
    if not candidates: return None
    candidates.sort(key=lambda x:x[0],reverse=True); score,title,info,ext=candidates[0]
    if score<1: return None
    fn=title.removeprefix("File:")
    return {"file_name":fn,"page_url":"https://commons.wikimedia.org/wiki/"+urllib.parse.quote(title.replace(" ","_"),safe=":()_,-."),"image_url":info.get("thumburl") or info.get("url"),"license":ext.get("LicenseShortName",{}).get("value","") ,"artist":ext.get("Artist",{}).get("value","") ,"method":"Commons search","qid":""}

def resolve(p):
    for t in p["titles"]:
        try:
            x=via_wikipedia(t)
            if x: return x
        except Exception: pass
    return commons_search(p["player"])

def face_crop(image):
    image=ImageOps.exif_transpose(image).convert("RGB"); arr=np.array(image); gray=cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)
    cascade=cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
    faces=cascade.detectMultiScale(gray,scaleFactor=1.08,minNeighbors=5,minSize=(40,40)); w,h=image.size
    if len(faces):
        x,y,fw,fh=max(faces,key=lambda f:int(f[2])*int(f[3])); cx=x+fw/2; cy=y+fh/2
        side=min(max(fw*3.0,fh*3.25),max(w,h)); l=int(cx-side/2); t=int(cy-side*0.43); r=l+int(side); b=t+int(side)
        if l<0:r-=l;l=0
        if t<0:b-=t;t=0
        if r>w:l-=r-w;r=w
        if b>h:t-=b-h;b=h
        crop=image.crop((max(0,l),max(0,t),min(w,r),min(h,b)))
        return ImageOps.fit(crop,(TARGET,TARGET),method=Image.Resampling.LANCZOS,centering=(.5,.46)),True
    return ImageOps.fit(image,(TARGET,TARGET),method=Image.Resampling.LANCZOS,centering=(.5,.34)),False

def save_png(image,path):
    best=None
    for side in (512,448,384,320):
        im=image if image.size==(side,side) else image.resize((side,side),Image.Resampling.LANCZOS)
        for colors in (192,128,96,64):
            q=im.quantize(colors=colors,method=Image.Quantize.MEDIANCUT); b=io.BytesIO(); q.save(b,"PNG",optimize=True); data=b.getvalue()
            if best is None or len(data)<len(best[0]): best=(data,side)
            if len(data)<=MAX_BYTES: path.write_bytes(data); return side,len(data)
    path.write_bytes(best[0]); return best[1],len(best[0])

def clean(s): return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",s or "")).strip()

def preview(rows):
    cols,card,label,pad=5,180,36,12; nr=math.ceil(len(rows)/cols); out=Image.new("RGB",(pad+cols*(card+pad),pad+nr*(card+label+pad)),"#f2f2f2"); d=ImageDraw.Draw(out); font=ImageFont.load_default()
    for i,row in enumerate(rows):
        rr,cc=divmod(i,cols); x=pad+cc*(card+pad); y=pad+rr*(card+label+pad)
        with Image.open(ROOT/row["filename"]) as im: tile=ImageOps.fit(im.convert("RGB"),(card,card),method=Image.Resampling.LANCZOS)
        out.paste(tile,(x,y)); d.text((x,y+card+7),row["filename"].removesuffix(".png")[:28],fill="#111",font=font)
    out.save(ROOT/"preview.jpg","JPEG",quality=90,optimize=True)

def main():
    if ROOT.exists(): shutil.rmtree(ROOT)
    ROOT.mkdir(); rows=[]; failures=[]
    for p in PLAYERS:
        print("Resolving",p["player"],flush=True)
        try:
            src=resolve(p)
            if not src: raise RuntimeError("No reusable image resolved")
            raw=download(src["image_url"])
            with Image.open(io.BytesIO(raw)) as im: proc,face=face_crop(im)
            side,size=save_png(proc,ROOT/p["file"])
            rows.append({"filename":p["file"],"person_name":p["player"],"width":side,"height":side,"size_bytes":size,"size_kb":round(size/1024,2),"status":"OK" if size<=MAX_BYTES else "OK_OVER_TARGET","face_detected":"yes" if face else "no","source_file":src.get("file_name",""),"source_url":src.get("page_url",""),"license":clean(src.get("license","")),"artist":clean(src.get("artist","")),"wikidata_id":src.get("qid",""),"resolution_method":src.get("method","")})
            print("OK",p["file"],round(size/1024,1),"KB face=",face,flush=True)
        except Exception as e:
            failures.append(f"{p['player']}: {type(e).__name__}: {e}"); print("FAILED",failures[-1],flush=True)
    fields=["filename","person_name","width","height","size_bytes","size_kb","status","face_detected","source_file","source_url","license","artist","wikidata_id","resolution_method"]
    with (ROOT/"manifest.csv").open("w",newline="",encoding="utf-8-sig") as h: w=csv.DictWriter(h,fieldnames=fields);w.writeheader();w.writerows(rows)
    if failures:(ROOT/"DOWNLOAD_FAILURES.txt").write_text("\n".join(failures)+"\n",encoding="utf-8")
    preview(rows)
    if ZIP_PATH.exists(): ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted(ROOT.iterdir()): z.write(f,arcname=f.name)
    print(f"Created {len(rows)}/{len(PLAYERS)} assets")
    return 0

if __name__=="__main__": raise SystemExit(main())
