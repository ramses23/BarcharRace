from __future__ import annotations
import csv, io, zipfile
from pathlib import Path
import requests
from PIL import Image, ImageOps

ROOT=Path('photo_pack_batch04')
ZIP_PATH=Path('football_player_photos_batch04_png_max130kb.zip')
MAX_BYTES=130*1024
FILE='riks_p_tersons.png'
IMAGE_URL='https://kazhe.lv/images/futbols/eriks-petersons.jpg'
PAGE_URL='https://kazhe.lv/futbols/personas/eriks-petersons'

def save_small(im,path):
    best=None
    for side in (512,448,384,320):
        x=ImageOps.fit(im.convert('RGB'),(side,side),method=Image.Resampling.LANCZOS,centering=(0.5,0.42))
        for colors in (192,128,96,64):
            q=x.quantize(colors=colors,method=Image.Quantize.MEDIANCUT); b=io.BytesIO(); q.save(b,'PNG',optimize=True); data=b.getvalue()
            if best is None or len(data)<len(best[0]): best=(data,side)
            if len(data)<=MAX_BYTES: path.write_bytes(data); return side,len(data)
    path.write_bytes(best[0]); return best[1],len(best[0])

def main():
    r=requests.get(IMAGE_URL,headers={'User-Agent':'BarcharRace-photo-pack/2.3'},timeout=120); r.raise_for_status()
    with Image.open(io.BytesIO(r.content)) as im:
        side,size=save_small(ImageOps.exif_transpose(im),ROOT/FILE)
    manifest=ROOT/'manifest.csv'
    with manifest.open('r',encoding='utf-8-sig',newline='') as h: rows=list(csv.DictReader(h))
    fields=['filename','person_name','width','height','size_bytes','size_kb','status','face_detected','source_file','source_url','license','artist','wikidata_id','resolution_method']
    rows=[x for x in rows if x.get('filename')!=FILE]
    rows.append({'filename':FILE,'person_name':'Ēriks Pētersons','width':side,'height':side,'size_bytes':size,'size_kb':round(size/1024,2),'status':'OK_LICENSE_UNCLEAR','face_detected':'source portrait','source_file':'eriks-petersons.jpg','source_url':PAGE_URL,'license':'License unclear; source site copyright notice applies','artist':'Photo from Latvian athletes collective passport for 1934 Sweden trip','wikidata_id':'','resolution_method':'Curated historical portrait from Futbols Latvijā 1907-1940'})
    rows.sort(key=lambda x:x['filename'])
    with manifest.open('w',encoding='utf-8-sig',newline='') as h: w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    failures=ROOT/'DOWNLOAD_FAILURES.txt'
    if failures.exists(): failures.unlink()
    # rebuild preview simply left as original; package all assets
    if ZIP_PATH.exists(): ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted(ROOT.iterdir()): z.write(f,arcname=f.name)
    pngs=list(ROOT.glob('*.png'))
    assert len(pngs)==20, f'Expected 20 PNGs, found {len(pngs)}'
    assert all(p.stat().st_size<=MAX_BYTES for p in pngs)
    print('Batch 04 patched: 20 PNGs, all <=130 KB')

if __name__=='__main__': main()
