from __future__ import annotations
import csv, io, zipfile
from pathlib import Path
import requests
from PIL import Image, ImageOps

ROOT=Path('photo_pack_batch03')
ZIP_PATH=Path('football_player_photos_batch03_png_max130kb.zip')
MAX_BYTES=130*1024
UA={'User-Agent':'BarcharRace-photo-pack/2.2'}

PATCHES=[
    {
      'file':'carlos_izaguirre.png','person':'Carlos Izaguirre',
      'url':'https://commons.wikimedia.org/wiki/Special:Redirect/file/Argentina_equipo_1919.jpg?width=1200',
      'page':'https://commons.wikimedia.org/wiki/File:Argentina_equipo_1919.jpg',
      'source':'Argentina equipo 1919.jpg','license':'Public domain',
      'crop':(0.57,0.43,0.82,1.0),
      'method':'Curated crop from Argentina 1919 team photo; Commons caption identifies Carlos Izaguirre fourth from left in front row.'
    },
    {
      'file':'jose_tognola.png','person':'José Tognola',
      'url':'https://commons.wikimedia.org/wiki/Special:Redirect/file/Uruguay_1916.jpg?width=1200',
      'page':'https://commons.wikimedia.org/wiki/File:Uruguay_1916.jpg',
      'source':'Uruguay 1916.jpg','license':'Public domain',
      'crop':(0.72,0.42,1.0,1.0),
      'method':'Curated crop from Uruguay 1916 team photo; Commons caption identifies José Tognola as the rightmost seated player.'
    },
    {
      'file':'tel_sforo_b_ez.png','person':'Telésforo Báez',
      'url':'https://commons.wikimedia.org/wiki/Special:Redirect/file/Brazil_vs_chile_1919.jpg?width=1200',
      'page':'https://commons.wikimedia.org/wiki/File:Brazil_vs_chile_1919.jpg',
      'source':'Brazil vs chile 1919.jpg','license':'Public domain',
      'crop':None,
      'method':'Historical match-photo fallback: Brazil v Chile, 11 May 1919; Telésforo Báez started for Chile. No reliable individual reusable portrait found.'
    },
]

def save_small(im,path):
    best=None
    for side in (512,448,384,320):
        x=ImageOps.fit(im.convert('RGB'),(side,side),method=Image.Resampling.LANCZOS)
        for colors in (192,128,96,64):
            q=x.quantize(colors=colors,method=Image.Quantize.MEDIANCUT); b=io.BytesIO(); q.save(b,'PNG',optimize=True); data=b.getvalue()
            if best is None or len(data)<len(best[0]): best=(data,side)
            if len(data)<=MAX_BYTES: path.write_bytes(data); return side,len(data)
    path.write_bytes(best[0]); return best[1],len(best[0])

def main():
    manifest=ROOT/'manifest.csv'
    with manifest.open('r',encoding='utf-8-sig',newline='') as h: rows=list(csv.DictReader(h))
    fields=['filename','person_name','width','height','size_bytes','size_kb','status','face_detected','source_file','source_url','license','artist','wikidata_id','resolution_method']
    for p in PATCHES:
        r=requests.get(p['url'],headers=UA,timeout=120); r.raise_for_status()
        with Image.open(io.BytesIO(r.content)) as im:
            im=ImageOps.exif_transpose(im).convert('RGB')
            if p['crop']:
                w,h=im.size; a,b,c,d=p['crop']; im=im.crop((int(a*w),int(b*h),int(c*w),int(d*h)))
            side,size=save_small(im,ROOT/p['file'])
        rows=[x for x in rows if x.get('filename')!=p['file']]
        rows.append({'filename':p['file'],'person_name':p['person'],'width':side,'height':side,'size_bytes':size,'size_kb':round(size/1024,2),'status':'OK_CURATED' if p['crop'] else 'OK_HISTORICAL_FALLBACK','face_detected':'curated' if p['crop'] else 'no','source_file':p['source'],'source_url':p['page'],'license':p['license'],'artist':'Unknown author','wikidata_id':'','resolution_method':p['method']})
    rows.sort(key=lambda x:x['filename'])
    with manifest.open('w',encoding='utf-8-sig',newline='') as h: w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    failures=ROOT/'DOWNLOAD_FAILURES.txt'
    if failures.exists(): failures.unlink()
    if ZIP_PATH.exists(): ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted(ROOT.iterdir()): z.write(f,arcname=f.name)
    pngs=list(ROOT.glob('*.png'))
    assert len(pngs)==20, f'Expected 20 PNGs, found {len(pngs)}'
    assert all(p.stat().st_size<=MAX_BYTES for p in pngs)
    print('Batch 03 patched: 20 PNGs, all <=130 KB')

if __name__=='__main__': main()
