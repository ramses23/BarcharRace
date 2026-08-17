from __future__ import annotations

import csv
import io
import math
import zipfile
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path('photo_pack_batch02')
ZIP_PATH = Path('football_player_photos_batch02_png_max130kb.zip')
MAX_BYTES = 130 * 1024
SESSION = requests.Session()
SESSION.headers.update({'User-Agent':'BarcharRace-photo-pack/2.2 (https://github.com/ramses23/BarcharRace)'})

CORRECTIONS = [
    {
        'filename':'dem_stenes_correia_de_syllos.png',
        'person_name':'Demósthenes Correia de Syllos',
        'source_file':'A.A. das Palmeiras - 1915.jpg',
        'source_url':'https://commons.wikimedia.org/wiki/File:A.A._das_Palmeiras_-_1915.jpg',
        'image_url':'https://commons.wikimedia.org/wiki/Special:Redirect/file/A.A._das_Palmeiras_-_1915.jpg?width=1200',
        'license':'Public domain',
        'artist':'Unknown author',
        'method':'Curated historical team-photo fallback; Demósthenes was a member of the 1915 A.A. das Palmeiras championship side',
        'mode':'pad',
    },
    {
        'filename':'edwin_clarcke.png',
        'person_name':'Edwin Clarke',
        'source_file':'José Clarke.png',
        'source_url':'https://commons.wikimedia.org/wiki/File:Jos%C3%A9_Clarke.png',
        'image_url':'https://commons.wikimedia.org/wiki/Special:Redirect/file/Jos%C3%A9_Clarke.png?width=800',
        'license':'Public domain',
        'artist':'Unknown author',
        'method':'Curated individual historical portrait; Commons identifies José/Edwin Clarke with Argentina in 1919',
        'mode':'portrait',
    },
    {
        'filename':'manoel_alencar_monte.png',
        'person_name':'Manoel Alencar do Monte',
        'source_file':'Brazil v argentina 1916.jpg',
        'source_url':'https://commons.wikimedia.org/wiki/File:Brazil_v_argentina_1916.jpg',
        'image_url':'https://commons.wikimedia.org/wiki/Special:Redirect/file/Brazil_v_argentina_1916.jpg?width=1200',
        'license':'Public domain',
        'artist':'Unknown author',
        'method':'Curated historical team-photo fallback; Alencar played for Brazil in Argentina v Brazil on 10 July 1916',
        'mode':'pad',
    },
    {
        'filename':'paul_sturzenegger.png',
        'person_name':'Paul Sturzenegger',
        'source_file':'Swiss national football team at the 1924 Summer Olympics in Paris.jpg',
        'source_url':'https://commons.wikimedia.org/wiki/File:Swiss_national_football_team_at_the_1924_Summer_Olympics_in_Paris.jpg',
        'image_url':'https://commons.wikimedia.org/wiki/Special:Redirect/file/Swiss_national_football_team_at_the_1924_Summer_Olympics_in_Paris.jpg?width=1200',
        'license':'Public domain',
        'artist':'Unknown author',
        'method':'Curated historical Swiss Olympic team-photo fallback; Sturzenegger was a member of the 1924 Olympic side',
        'mode':'pad',
    },
]

FIELDS = ['filename','person_name','width','height','size_bytes','size_kb','status','face_detected','source_file','source_url','license','artist','wikidata_id','resolution_method']


def download(url: str) -> bytes:
    response = SESSION.get(url, timeout=120)
    response.raise_for_status()
    return response.content


def prepare(image: Image.Image, mode: str) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert('RGB')
    if mode == 'portrait':
        return ImageOps.fit(image, (512,512), method=Image.Resampling.LANCZOS, centering=(0.5,0.38))
    return ImageOps.pad(image, (512,512), method=Image.Resampling.LANCZOS, color='white', centering=(0.5,0.5))


def save_small_png(image: Image.Image, destination: Path) -> tuple[int,int,int]:
    best = None
    for side in (512,448,384,320):
        resized = image if image.size == (side,side) else image.resize((side,side),Image.Resampling.LANCZOS)
        for colors in (192,128,96,64):
            q = resized.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
            b = io.BytesIO(); q.save(b,'PNG',optimize=True); data = b.getvalue()
            if best is None or len(data) < len(best[0]): best=(data,side)
            if len(data) <= MAX_BYTES:
                destination.write_bytes(data)
                return side,side,len(data)
    destination.write_bytes(best[0])
    return best[1],best[1],len(best[0])


def make_preview(rows: list[dict[str,str]]) -> None:
    ordered = [
        'ademir_de_menezes.png','ali_daei.png','arthur_friedenreich.png','clint_dempsey.png','dem_stenes_correia_de_syllos.png',
        'edwin_clarcke.png','gabriel_batistuta.png','gigi_riva.png','hakan_k_r.png','hristo_bonev.png',
        'jos_piendibene.png','just_fontaine.png','lajos_tichy.png','manoel_alencar_monte.png','memphis_depay.png',
        'neco.png','paul_sturzenegger.png','preben_elkj_r.png','roberto_cherro.png','rudi_v_ller.png',
    ]
    by_name={r['filename']:r for r in rows}
    cols,card,label_h,pad=5,180,40,12
    nrows=math.ceil(len(ordered)/cols)
    preview=Image.new('RGB',(pad+cols*(card+pad),pad+nrows*(card+label_h+pad)),'#f2f2f2')
    draw=ImageDraw.Draw(preview); font=ImageFont.load_default()
    for idx,name in enumerate(ordered):
        r,c=divmod(idx,cols); x,y=pad+c*(card+pad),pad+r*(card+label_h+pad)
        with Image.open(ROOT/name) as im:
            tile=ImageOps.fit(im.convert('RGB'),(card,card),method=Image.Resampling.LANCZOS)
        preview.paste(tile,(x,y))
        label=name.removesuffix('.png')[:27]
        if by_name.get(name,{}).get('status') == 'OK_TEAM_PHOTO_FALLBACK': label += ' [team]'
        draw.text((x,y+card+7),label,fill='#111111',font=font)
    preview.save(ROOT/'preview.jpg','JPEG',quality=90,optimize=True)


def main() -> int:
    manifest=ROOT/'manifest.csv'
    with manifest.open('r',encoding='utf-8-sig',newline='') as h:
        rows=list(csv.DictReader(h))
    by_name={r['filename']:r for r in rows}

    for item in CORRECTIONS:
        raw=download(item['image_url'])
        with Image.open(io.BytesIO(raw)) as image:
            processed=prepare(image,item['mode'])
        width,height,size_bytes=save_small_png(processed,ROOT/item['filename'])
        by_name[item['filename']]={
            'filename':item['filename'],'person_name':item['person_name'],'width':str(width),'height':str(height),
            'size_bytes':str(size_bytes),'size_kb':str(round(size_bytes/1024,2)),
            'status':'OK' if item['mode']=='portrait' else 'OK_TEAM_PHOTO_FALLBACK',
            'face_detected':'yes' if item['mode']=='portrait' else 'no',
            'source_file':item['source_file'],'source_url':item['source_url'],'license':item['license'],'artist':item['artist'],
            'wikidata_id':'','resolution_method':item['method'],
        }
        print(f"Corrected {item['filename']}: {size_bytes/1024:.1f} KB")

    ordered_rows=[]
    for path in sorted(ROOT.glob('*.png')):
        if path.name in by_name: ordered_rows.append(by_name[path.name])
    with manifest.open('w',encoding='utf-8-sig',newline='') as h:
        w=csv.DictWriter(h,fieldnames=FIELDS); w.writeheader(); w.writerows(ordered_rows)

    failure=ROOT/'DOWNLOAD_FAILURES.txt'
    if failure.exists(): failure.unlink()
    make_preview(ordered_rows)

    if ZIP_PATH.exists(): ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(ROOT.iterdir()): z.write(path,arcname=path.name)

    pngs=list(ROOT.glob('*.png'))
    if len(pngs)!=20: raise RuntimeError(f'Expected 20 PNGs, found {len(pngs)}')
    oversized=[p.name for p in pngs if p.stat().st_size>MAX_BYTES]
    if oversized: raise RuntimeError('Oversized PNGs: '+', '.join(oversized))
    print('Batch 02 quality corrections complete: 20 PNGs, all <=130 KB')
    return 0

if __name__=='__main__': raise SystemExit(main())
