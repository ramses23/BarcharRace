from __future__ import annotations

import csv
import io
import math
import re
import shutil
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

USER_AGENT = "BarcharRace-photo-pack/2.1 (https://github.com/ramses23/BarcharRace; BarChartStudio asset preparation)"
MAX_BYTES = 130 * 1024
TARGET = 512

PLAYERS: list[dict[str, str]] = [
    {"player": "Ademir de Menezes", "file": "ademir_de_menezes.png", "wikipedia": "Ademir de Menezes"},
    {"player": "Ali Daei", "file": "ali_daei.png", "wikipedia": "Ali Daei"},
    {"player": "Arthur Friedenreich", "file": "arthur_friedenreich.png", "wikipedia": "Arthur Friedenreich"},
    {"player": "Clint Dempsey", "file": "clint_dempsey.png", "wikipedia": "Clint Dempsey"},
    {"player": "Demósthenes Correia de Syllos", "file": "dem_stenes_correia_de_syllos.png", "wikipedia": "Demóstenes (footballer)"},
    {"player": "Edwin Clarke", "file": "edwin_clarcke.png", "wikipedia": "Edwin Clarke"},
    {"player": "Gabriel Batistuta", "file": "gabriel_batistuta.png", "wikipedia": "Gabriel Batistuta"},
    {"player": "Gigi Riva", "file": "gigi_riva.png", "wikipedia": "Gigi Riva"},
    {"player": "Hakan Şükür", "file": "hakan_k_r.png", "wikipedia": "Hakan Şükür"},
    {"player": "Hristo Bonev", "file": "hristo_bonev.png", "wikipedia": "Hristo Bonev"},
    {"player": "José Piendibene", "file": "jos_piendibene.png", "wikipedia": "José Piendibene"},
    {"player": "Just Fontaine", "file": "just_fontaine.png", "wikipedia": "Just Fontaine"},
    {"player": "Lajos Tichy", "file": "lajos_tichy.png", "wikipedia": "Lajos Tichy"},
    {"player": "Manoel Alencar do Monte", "file": "manoel_alencar_monte.png", "wikipedia": "Alencar (footballer, born 1892)"},
    {"player": "Memphis Depay", "file": "memphis_depay.png", "wikipedia": "Memphis Depay"},
    {"player": "Neco", "file": "neco.png", "wikipedia": "Neco"},
    {"player": "Paul Sturzenegger", "file": "paul_sturzenegger.png", "wikipedia": "Paul Sturzenegger"},
    {"player": "Preben Elkjær", "file": "preben_elkj_r.png", "wikipedia": "Preben Elkjær"},
    {"player": "Roberto Cherro", "file": "roberto_cherro.png", "wikipedia": "Roberto Cherro"},
    {"player": "Rudi Völler", "file": "rudi_v_ller.png", "wikipedia": "Rudi Völler"},
]

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def get_json(url: str, params: dict[str, Any] | None = None, attempts: int = 5) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            r = SESSION.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(min(2**attempt, 12))
    raise RuntimeError(f"JSON request failed: {url}: {last}")


def download_bytes(url: str, attempts: int = 5) -> bytes:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            r = SESSION.get(url, timeout=120)
            r.raise_for_status()
            return r.content
        except Exception as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(min(2**attempt, 12))
    raise RuntimeError(f"Image download failed: {url}: {last}")


def wikipedia_wikidata_id(title: str) -> str | None:
    data = get_json("https://en.wikipedia.org/w/api.php", {"action":"query","format":"json","redirects":1,"prop":"pageprops","titles":title})
    page = next(iter(data["query"]["pages"].values()))
    return page.get("pageprops", {}).get("wikibase_item")


def wikidata_p18(qid: str) -> str | None:
    data = get_json(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
    claims = data["entities"][qid].get("claims", {}).get("P18", [])
    if claims:
        try:
            return claims[0]["mainsnak"]["datavalue"]["value"]
        except Exception:
            pass
    return None


def commons_image_info(file_name: str) -> dict[str, Any]:
    title = "File:" + file_name
    data = get_json("https://commons.wikimedia.org/w/api.php", {"action":"query","format":"json","prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1400,"titles":title})
    page = next(iter(data["query"]["pages"].values()))
    infos = page.get("imageinfo", [])
    if not infos:
        raise RuntimeError(f"No Commons imageinfo for {file_name}")
    info = infos[0]
    ext = info.get("extmetadata", {})
    return {
        "file_name": file_name,
        "page_url": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe=":()_,-."),
        "image_url": info.get("thumburl") or info.get("url"),
        "license": ext.get("LicenseShortName", {}).get("value", ""),
        "artist": ext.get("Artist", {}).get("value", ""),
    }


def wikipedia_pageimage(title: str) -> tuple[str, str] | None:
    data = get_json("https://en.wikipedia.org/w/api.php", {"action":"query","format":"json","redirects":1,"prop":"pageimages","piprop":"thumbnail|name","pithumbsize":1400,"titles":title})
    page = next(iter(data["query"]["pages"].values()))
    thumb = page.get("thumbnail", {}).get("source")
    name = page.get("pageimage")
    return (name, thumb) if name and thumb else None


def commons_search(query: str) -> dict[str, Any] | None:
    data = get_json("https://commons.wikimedia.org/w/api.php", {
        "action":"query","format":"json","generator":"search","gsrnamespace":6,"gsrlimit":12,
        "gsrsearch":query,"prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1400,
    })
    pages = list(data.get("query", {}).get("pages", {}).values())
    if not pages:
        return None
    terms = {t.lower() for t in re.findall(r"[A-Za-zÀ-ÿ]+", query) if len(t) > 2}
    scored = []
    for page in pages:
        title = page.get("title", "")
        info = (page.get("imageinfo") or [{}])[0]
        if not info.get("thumburl") and not info.get("url"):
            continue
        low = title.lower()
        score = sum(3 for t in terms if t in low)
        if any(k in low for k in ("portrait", "head", "cropped", "face")):
            score += 4
        if any(k in low for k in ("team", "squad", "lineup", "group")):
            score -= 4
        scored.append((score, title, info))
    if not scored:
        return None
    _, title, info = max(scored, key=lambda x: x[0])
    ext = info.get("extmetadata", {})
    return {
        "file_name": title.removeprefix("File:"),
        "page_url": "https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe=":()_,-."),
        "image_url": info.get("thumburl") or info.get("url"),
        "license": ext.get("LicenseShortName", {}).get("value", ""),
        "artist": ext.get("Artist", {}).get("value", ""),
        "resolution_method": "Commons search",
    }


def resolve_source(player: dict[str, str]) -> dict[str, Any]:
    title = player["wikipedia"]
    try:
        qid = wikipedia_wikidata_id(title)
    except Exception:
        qid = None
    if qid:
        p18 = wikidata_p18(qid)
        if p18:
            info = commons_image_info(p18)
            info.update({"wikidata_id": qid, "resolution_method": "Wikidata P18"})
            return info
    try:
        fallback = wikipedia_pageimage(title)
    except Exception:
        fallback = None
    if fallback:
        file_name, thumb_url = fallback
        try:
            info = commons_image_info(file_name)
        except Exception:
            info = {"file_name":file_name,"page_url":"https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),"image_url":thumb_url,"license":"","artist":""}
        info.update({"wikidata_id": qid or "", "resolution_method": "Wikipedia pageimage"})
        return info
    for query in (player["player"] + " portrait", player["player"] + " footballer", player["player"]):
        found = commons_search(query)
        if found:
            found.update({"wikidata_id": qid or ""})
            return found
    raise RuntimeError(f"No reusable image resolved for {player['player']}")


def face_crop(image: Image.Image) -> tuple[Image.Image, bool]:
    image = ImageOps.exif_transpose(image).convert("RGB")
    rgb = np.array(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=5, minSize=(35,35))
    w, h = image.size
    if len(faces):
        x,y,fw,fh = max(faces, key=lambda f:int(f[2])*int(f[3]))
        cx, cy = x + fw/2, y + fh/2
        side = min(max(fw*3.0, fh*3.2), max(w,h))
        left, top = int(cx-side/2), int(cy-side*0.43)
        right, bottom = left+int(side), top+int(side)
        if left < 0: right -= left; left = 0
        if top < 0: bottom -= top; top = 0
        if right > w: left -= right-w; right = w
        if bottom > h: top -= bottom-h; bottom = h
        crop = image.crop((max(0,left),max(0,top),min(w,right),min(h,bottom)))
        return ImageOps.fit(crop,(TARGET,TARGET),method=Image.Resampling.LANCZOS,centering=(0.5,0.46)), True
    return ImageOps.fit(image,(TARGET,TARGET),method=Image.Resampling.LANCZOS,centering=(0.5,0.34)), False


def save_small_png(image: Image.Image, destination: Path) -> tuple[int,int,int]:
    best = None
    for side in (512,448,384,320):
        resized = image if image.size == (side,side) else image.resize((side,side),Image.Resampling.LANCZOS)
        for colors in (192,128,96,64):
            q = resized.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
            buf = io.BytesIO(); q.save(buf,"PNG",optimize=True); data = buf.getvalue()
            if best is None or len(data) < len(best[0]): best = (data,side)
            if len(data) <= MAX_BYTES:
                destination.write_bytes(data); return side,side,len(data)
    destination.write_bytes(best[0]); return best[1],best[1],len(best[0])


def clean_html(value: str) -> str:
    return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",value or "")).strip()


def make_preview(rows: list[dict[str, Any]], root: Path) -> None:
    cols, card, label_h, pad = 5, 180, 36, 12
    nrows = math.ceil(len(rows)/cols)
    preview = Image.new("RGB",(pad+cols*(card+pad),pad+nrows*(card+label_h+pad)),"#f2f2f2")
    draw = ImageDraw.Draw(preview); font = ImageFont.load_default()
    for idx,row in enumerate(rows):
        r,c = divmod(idx,cols); x,y = pad+c*(card+pad), pad+r*(card+label_h+pad)
        with Image.open(root/row["filename"]) as im:
            tile = ImageOps.fit(im.convert("RGB"),(card,card),method=Image.Resampling.LANCZOS)
        preview.paste(tile,(x,y)); draw.text((x,y+card+7),row["filename"].removesuffix(".png")[:28],fill="#111111",font=font)
    preview.save(root/"preview.jpg","JPEG",quality=90,optimize=True)


def main() -> int:
    root = Path("photo_pack_batch02")
    if root.exists(): shutil.rmtree(root)
    root.mkdir()
    rows=[]; failures=[]
    for player in PLAYERS:
        print(f"Resolving {player['player']}...", flush=True)
        try:
            source = resolve_source(player)
            raw = download_bytes(source["image_url"])
            with Image.open(io.BytesIO(raw)) as image:
                processed, face_found = face_crop(image)
            dest = root/player["file"]
            width,height,size_bytes = save_small_png(processed,dest)
            rows.append({"filename":player["file"],"person_name":player["player"],"width":width,"height":height,"size_bytes":size_bytes,"size_kb":round(size_bytes/1024,2),"status":"OK" if size_bytes<=MAX_BYTES else "OK_OVER_TARGET","face_detected":"yes" if face_found else "no","source_file":source.get("file_name",""),"source_url":source.get("page_url",""),"license":clean_html(source.get("license","")),"artist":clean_html(source.get("artist","")),"wikidata_id":source.get("wikidata_id",""),"resolution_method":source.get("resolution_method","")})
            print(f"OK {player['file']} {size_bytes/1024:.1f} KB face={face_found}", flush=True)
        except Exception as exc:
            msg=f"{player['player']}: {type(exc).__name__}: {exc}"; failures.append(msg); print("FAILED "+msg, flush=True)
    fields=["filename","person_name","width","height","size_bytes","size_kb","status","face_detected","source_file","source_url","license","artist","wikidata_id","resolution_method"]
    with (root/"manifest.csv").open("w",newline="",encoding="utf-8-sig") as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    if failures: (root/"DOWNLOAD_FAILURES.txt").write_text("\n".join(failures)+"\n",encoding="utf-8")
    make_preview(rows,root)
    zip_path=Path("football_player_photos_batch02_png_max130kb.zip")
    if zip_path.exists(): zip_path.unlink()
    with zipfile.ZipFile(zip_path,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.iterdir()): z.write(p,arcname=p.name)
    expected={p["file"] for p in PLAYERS}; created={r["filename"] for r in rows}; missing=sorted(expected-created)
    print(f"Created {len(created)}/{len(expected)} player assets.")
    if missing: print("Missing: "+", ".join(missing)); return 2
    return 0

if __name__ == "__main__": raise SystemExit(main())
