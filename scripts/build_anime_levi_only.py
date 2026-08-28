from pathlib import Path
import csv, io, zipfile, requests
from PIL import Image, ImageDraw, ImageFont
from rembg import remove

API='https://graphql.anilist.co'
UA='BarChartStudioAssetBuilder/1.0'
MAX_BYTES=130*1024
CANVAS=512
PAD=26
OUT=Path('anime_levi_only')
OUT.mkdir(exist_ok=True)
ZIP=Path('anime_levi_only_png_max130kb.zip')
PREVIEW=Path('anime_levi_only_preview.jpg')
QUERY='''query($search:String){Character(search:$search){id name{full native alternative} image{large medium} siteUrl media(perPage:10){nodes{title{romaji english native}}}}}'''


def lookup(search):
    r=requests.post(API,json={'query':QUERY,'variables':{'search':search}},headers={'User-Agent':UA,'Accept':'application/json','Content-Type':'application/json'},timeout=60)
    r.raise_for_status()
    p=r.json()
    if p.get('errors'):
        raise RuntimeError(str(p['errors']))
    return (p.get('data') or {}).get('Character')


def process(raw,out):
    src=Image.open(io.BytesIO(raw)).convert('RGBA')
    cut=remove(src).convert('RGBA')
    bbox=cut.getbbox()
    if not bbox:
        raise RuntimeError('empty cutout')
    cut=cut.crop(bbox)
    maxside=CANVAS-2*PAD
    scale=min(maxside/cut.width,maxside/cut.height)
    nw=max(1,int(cut.width*scale)); nh=max(1,int(cut.height*scale))
    cut=cut.resize((nw,nh),Image.Resampling.LANCZOS)
    canv=Image.new('RGBA',(CANVAS,CANVAS),(255,255,255,0))
    x=(CANVAS-nw)//2
    y=max(PAD,(CANVAS-nh)//2-12)
    y=min(y,CANVAS-PAD-nh)
    canv.alpha_composite(cut,(x,y))
    for colors in (256,192,160,128,96,80,64,48):
        q=canv.quantize(colors=colors,method=Image.Quantize.FASTOCTREE)
        q.save(out,'PNG',optimize=True)
        if out.stat().st_size<=MAX_BYTES:
            return colors
    return colors

c=lookup('Levi')
if not c:
    raise RuntimeError('AniList no result for Levi')
# Validate Attack on Titan / Shingeki no Kyojin appears in media.
titles=[]
for m in ((c.get('media') or {}).get('nodes') or []):
    t=m.get('title') or {}
    titles += [x for x in (t.get('english'),t.get('romaji'),t.get('native')) if x]
joined=' | '.join(titles).lower()
if 'attack on titan' not in joined and 'shingeki no kyojin' not in joined:
    raise RuntimeError('Series verification failed: '+ ' | '.join(titles[:8]))
selected=(c.get('image') or {}).get('large') or (c.get('image') or {}).get('medium')
if not selected:
    raise RuntimeError('No direct asset URL')
rr=requests.get(selected,headers={'User-Agent':UA},timeout=60)
rr.raise_for_status()
out=OUT/'levi_ackerman.png'
colors=process(rr.content,out)
size=out.stat().st_size
Image.open(out).verify()
if size>MAX_BYTES:
    raise RuntimeError(f'Output too large: {size}')

manifest=[{
    'filename':'levi_ackerman.png','entity':'Levi Ackerman','series':'Attack on Titan','entity_type':'fictional_character','role':'primary','status':'OK',
    'source_page_url':c.get('siteUrl') or '', 'direct_asset_url':selected, 'source_type':'AniList character database',
    'license_note':'Authentic franchise character image located via AniList; reuse rights not asserted.',
    'width':CANVAS,'height':CANVAS,'size_bytes':size,'size_kb':round(size/1024,2),'background_removed':'yes','canvas':'512x512',
    'notes':f"Alias search=Levi; matched={c.get('name',{}).get('full')}; palette={colors}; media="+' | '.join(titles[:6])
}]
with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=manifest[0].keys()); w.writeheader(); w.writerows(manifest)
with (OUT/'SEARCH_REPORT.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['filename','entity','query','candidate_count','selected_source','selection_reason','rejected_notes']);
    w.writerow(['levi_ackerman.png','Levi Ackerman','"Levi" "Attack on Titan" authentic character portrait; AniList alias search=Levi',1,selected,'Matched Levi and verified Attack on Titan media',''])
with (OUT/'ASSET_ATTRIBUTION.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['filename','entity','source_page_url','author_or_owner','license','license_url','attribution_text','rights_note']);
    w.writerow(['levi_ackerman.png','Levi Ackerman',c.get('siteUrl') or '','Underlying franchise rights holder','Not specified by AniList','','Source URL retained for provenance.','Copyright/reuse rights not guaranteed.'])

prev=Image.new('RGB',(560,610),(245,245,245))
img=Image.open(out).convert('RGBA')
white=Image.new('RGBA',img.size,(255,255,255,255)); white.alpha_composite(img)
img=white.convert('RGB').resize((500,500),Image.Resampling.LANCZOS)
prev.paste(img,(30,30))
d=ImageDraw.Draw(prev)
try: font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',24)
except: font=ImageFont.load_default()
d.text((30,545),'levi_ackerman.png',fill=(20,20,20),font=font)
prev.save(PREVIEW,quality=92)

with zipfile.ZipFile(ZIP,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(OUT.iterdir()): z.write(p,arcname=p.name)
    z.write(PREVIEW,arcname='asset_pack_preview.jpg')
print(f'OK {out} {size} bytes source={selected}')
