from __future__ import annotations

import csv, io, math, re, shutil, time, urllib.parse, zipfile
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

USER_AGENT = "BarcharRace-photo-pack/2.4 (https://github.com/ramses23/BarcharRace; BarChartStudio asset preparation)"
MAX_BYTES = 130 * 1024
TARGET = 512
ROOT = Path("photo_pack_batch05")
ZIP_PATH = Path("football_player_photos_batch05_png_max130kb.zip")

PLAYERS = [
    {"player":"Héctor Castro","file":"h_ctor_castro.png","titles":["Héctor Castro"]},
    {"player":"Herminio Masantonio","file":"herminio_masantonio.png","titles":["Herminio Masantonio"]},
    {"player":"Isabelino Gradín","file":"isabelino_grad_n.png","titles":["Isabelino Gradín"]},
    {"player":"Jared Borgetti","file":"jared_borgetti.png","titles":["Jared Borgetti"]},
    {"player":"José Manuel Moreno","file":"jos_manuel_moreno.png","titles":["José Manuel Moreno"]},
    {"player":"Julio Francia","file":"julio_francia.png","titles":["Julio Francia"]},
    {"player":"Kazuyoshi Miura","file":"kazuyoshi_miura.png","titles":["Kazuyoshi Miura"]},
    {"player":"Luis Suárez","file":"luis_su_rez.png","titles":["Luis Suárez (Uruguayan footballer)","Luis Suárez"]},
    {"player":"Marko Arnautović","file":"marko_arnautovi.png","titles":["Marko Arnautović"]},
    {"player":"Miroslav Klose","file":"miroslav_klose.png","titles":["Miroslav Klose"]},
    {"player":"Norberto Doroteo Méndez","file":"norberto_doroteo_m_ndez.png","titles":["Norberto Méndez","Norberto Doroteo Méndez"]},
    {"player":"Pedro Petrone","file":"pedro_petrone.png","titles":["Pedro Petrone"]},
    {"player":"Robbie Keane","file":"robbie_keane.png","titles":["Robbie Keane"]},
    {"player":"Romelu Lukaku","file":"romelu_lukaku.png","titles":["Romelu Lukaku"]},
    {"player":"Óscar Míguez","file":"scar_m_guez.png","titles":["Óscar Míguez"]},
    {"player":"Thierry Henry","file":"thierry_henry.png","titles":["Thierry Henry"]},
    {"player":"Zlatan Ibrahimović","file":"zlatan_ibrahimovi.png","titles":["Zlatan Ibrahimović"]},
    {"player":"Aleksandar Mitrović","file":"aleksandar_mitrovi.png","titles":["Aleksandar Mitrović"]},
    {"player":"Antonio Blanco","file":"antonio_blanco.png","titles":["Antonio Blanco (footballer)","Antonio Blanco"]},
    {"player":"Carlos Scarone","file":"carlos_scarone.png","titles":["Carlos Scarone"]},
]

S = requests.Session(); S.headers.update({"User-Agent": USER_AGENT})

def get_json(url, params=None, attempts=6):
    last=None
    for i in range(attempts):
        try:
            r=S.get(url, params=params, timeout=60)
            if r.status_code == 429:
                time.sleep(min(3*(i+1),18)); continue
            r.raise_for_status(); time.sleep(0.25); return r.json()
        except Exception as e:
            last=e; time.sleep(min(2**i,12))
    raise RuntimeError(f"request failed {url}: {last}")

def download(url, attempts=7):
    last=None
    for i in range(attempts):
        try:
            r=S.get(url,timeout=120)
            if r.status_code == 429:
                time.sleep(min(5*(i+1),30)); continue
            r.raise_for_status(); time.sleep(0.5); return r.content
        except Exception as e:
            last=e; time.sleep(min(3*(i+1),20))
    raise RuntimeError(f"download failed: {last}")

def commons_info(file_name):
    data=get_json("https://commons.wikimedia.org/w/api.php",{"action":"query","format":"json","prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1200,"titles":"File:"+file_name})
    page=next(iter(data["query"]["pages"].values())); infos=page.get("imageinfo",[])
    if not infos: raise RuntimeError("no imageinfo")
    info=infos[0]; ext=info.get("extmetadata",{})
    return {"file_name":file_name,"page_url":"https://commons.wikimedia.org/wiki/"+urllib.parse.quote(("File:"+file_name).replace(" ","_"),safe=":()_,-."),"image_url":info.get("thumburl") or info.get("url"),"license":ext.get("LicenseShortName",{}).get("value","") ,"artist":ext.get("Artist",{}).get("value","")}

def via_wikipedia(title):
    data=get_json("https://en.wikipedia.org/w/api.php",{"action":"query","format":"json","redirects":1,"prop":"pageprops|pageimages","piprop":"thumbnail|name","pithumbsize":1200,"titles":title})
    page=next(iter(data["query"]["pages"].values()))
    if "missing" in page: return None
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
    data=get_json("https://commons.wikimedia.org/w/api.php",{"action":"query","format":"json","generator":"search","gsrsearch":query+" footballer","gsrnamespace":6,"gsrlimit":12,"prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1200})
    pages=data.get("query",{}).get("pages",{})
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
        except Exception as e:
            print(" title lookup warning",t,type(e).__name__,flush=True)
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
            rows.append({"filename":p["file"],"person_name":p["player"],"width":side,"height":side,"size_bytes":size,"size_kb":round(size/1024,2),"status":"OK" if size<=MAX_BYTES else "OK_OVER_TARGET","face_detected":"yes" if face else "no","source_file":src.get("file_name",""),"source_url":src.get("page_url","") ,"license":clean(src.get("license","")),"artist":clean(src.get("artist","")),"wikidata_id":src.get("qid",""),"resolution_method":src.get("method","")})
            print("OK",p["file"],round(size/1024,1),"KB face=",face,flush=True)
        except Exception as e:
            failures.append(f"{p['player']}: {type(e).__name__}: {e}"); print("FAILED",failures[-1],flush=True)
        time.sleep(0.75)
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
