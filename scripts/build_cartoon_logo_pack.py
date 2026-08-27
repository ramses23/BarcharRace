from __future__ import annotations

import csv
import io
import math
import re
import time
import zipfile
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

OUT = Path('cartoon_logo_pack')
ZIP = Path('cartoon_logos_png_max130kb.zip')
PREVIEW = Path('cartoon_logos_preview.jpg')
MAX_BYTES = 130 * 1024
CANVAS = (512, 256)
UA = {'User-Agent': 'BarcharRace-cartoon-logo-pack/1.0 (BarChartStudio asset builder)'}
S = requests.Session(); S.headers.update(UA)

ITEMS = [
    ('adventure_time.png','Adventure Time'),
    ('bugs_bunny.png','Bugs Bunny'),
    ('ducktales.png','DuckTales'),
    ('gumball.png','The Amazing World of Gumball'),
    ('paw_patrol.png','PAW Patrol'),
    ('regular_show.png','Regular Show'),
    ('teen_titans_go.png','Teen Titans Go!'),
    ('woody_woodpecker.png','Woody Woodpecker'),
    ('animaniacs.png','Animaniacs'),
    ('cocomelon.png','CoComelon'),
    ('ed_edd_n_eddy.png','Ed, Edd n Eddy'),
    ('looney_tunes.png','Looney Tunes'),
    ('peppa_pig.png','Peppa Pig'),
    ('rick_and_morty.png','Rick and Morty'),
    ('the_flintstones.png','The Flintstones'),
    ('yogi_bear.png','Yogi Bear'),
    ('arthur.png','Arthur TV series'),
    ('courage.png','Courage the Cowardly Dog'),
    ('family_guy.png','Family Guy'),
    ('masha_and_bear.png','Masha and the Bear'),
    ('phineas_and_ferb.png','Phineas and Ferb'),
    ('scooby_doo.png','Scooby-Doo'),
    ('the_jetsons.png','The Jetsons'),
    ('avatar_last_airbender.png','Avatar The Last Airbender'),
    ('dexters_laboratory.png,"Dexter's Laboratory"),
    ('felix_the_cat.png','Felix the Cat'),
    ('mickey_mouse.png','Mickey Mouse'),
    ('pink_panther.png','The Pink Panther'),
    ('south_park.png','South Park'),
    ('the_simpsons.png','The Simpsons'),
    ('batman_tas.png','Batman The Animated Series'),
    ('dora_explorer.png','Dora the Explorer'),
    ('futurama.png','Futurama'),
    ('miraculous_ladybug.png','Miraculous Ladybug'),
    ('pokemon_tv.png','Pokémon anime'),
    ('spongebob.png','SpongeBob SquarePants'),
    ('tmnt.png','Teenage Mutant Ninja Turtles'),
    ('bluey.png','Bluey TV series'),
    ('dragon_ball_z.png','Dragon Ball Z'),
    ('gravity_falls.png','Gravity Falls'),
    ('mlp_friendship.png','My Little Pony Friendship Is Magic'),
    ('popeye.png','Popeye'),
    ('steven_universe.png','Steven Universe'),
    ('tom_and_jerry.png','Tom and Jerry'),
]

COMMONS = 'https://commons.wikimedia.org/w/api.php'
ENWIKI = 'https://en.wikipedia.org/w/api.php'


def req(url, params=None, attempts=4):
    last=None
    for i in range(attempts):
        try:
            r=S.get(url,params=params,timeout=45)
            if r.status_code==429:
                raise RuntimeError('429 rate limit')
            r.raise_for_status()
            return r
        except Exception as e:
            last=e; time.sleep(min(2**i,10))
    raise RuntimeError(f'request failed {url}: {last}')


def norm(s: str) -> str:
    s=s.lower().replace('&',' and ')
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return ' '.join(s.split())

STOP={'the','a','an','and','tv','series','anime'}
BAD={'poster','screenshot','episode','dvd','cover','wallpaper','cosplay','costume','toy','plush','figurine','mural','stamp','coin','car','building'}
GOOD={'logo','wordmark','title','logotype','brand'}


def score_candidate(file_title: str, display: str, mime: str, width: int, height: int) -> int:
    ft=norm(file_title.replace('File:',''))
    dn=norm(display)
    tokens=[t for t in dn.split() if t not in STOP and len(t)>1]
    score=0
    if 'logo' in ft: score += 80
    if 'wordmark' in ft or 'logotype' in ft: score += 55
    if 'title' in ft: score += 25
    matched=sum(1 for t in tokens if t in ft)
    score += matched * 9
    if tokens and matched >= max(1,len(tokens)-1): score += 30
    for b in BAD:
        if b in ft: score -= 55
    if mime in ('image/svg+xml','image/png'): score += 18
    if width and height:
        if width >= 500: score += 8
        if width >= height: score += 6
    return score


def search_api(api: str, display: str):
    results=[]
    queries=[f'{display} logo', f'{display} wordmark', f'{display} title logo']
    seen=set()
    for q in queries:
        try:
            data=req(api,{
                'action':'query','format':'json','generator':'search','gsrsearch':q,
                'gsrnamespace':6,'gsrlimit':12,'prop':'imageinfo',
                'iiprop':'url|size|mime|extmetadata','iiurlwidth':1400
            }).json()
        except Exception:
            continue
        for p in (data.get('query',{}).get('pages',{}) or {}).values():
            title=p.get('title','')
            if title in seen: continue
            seen.add(title)
            ii=(p.get('imageinfo') or [{}])[0]
            url=ii.get('thumburl') or ii.get('url')
            if not url: continue
            width=int(ii.get('thumbwidth') or ii.get('width') or 0)
            height=int(ii.get('thumbheight') or ii.get('height') or 0)
            mime=ii.get('mime','')
            ext=ii.get('extmetadata') or {}
            results.append({
                'file_title':title,'media_url':url,'description_url':ii.get('descriptionurl',''),
                'width':width,'height':height,'mime':mime,
                'license':(ext.get('LicenseShortName') or {}).get('value',''),
                'artist':re.sub('<[^>]+>',' ',(ext.get('Artist') or {}).get('value','')).strip(),
                'score':score_candidate(title,display,mime,width,height),
                'api':'commons' if 'commons.wikimedia' in api else 'enwiki'
            })
        time.sleep(0.25)
    return results


def choose(display: str):
    cand=search_api(COMMONS,display)+search_api(ENWIKI,display)
    cand.sort(key=lambda x:x['score'],reverse=True)
    # Require a plausible logo-ish candidate. Strong exact token matches without logo keyword are allowed.
    for c in cand:
        if c['score'] >= 65:
            return c
    if cand:
        return cand[0]
    return None


def trim_rgba(im: Image.Image) -> Image.Image:
    im=ImageOps.exif_transpose(im).convert('RGBA')
    # If image has real transparency, crop to alpha bbox.
    alpha=im.getchannel('A')
    bbox=alpha.getbbox()
    if bbox: im=im.crop(bbox)
    return im


def normalize_image(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as src:
        im=trim_rgba(src)
    # Remove obvious uniform white outer border only, conservatively.
    if im.mode=='RGBA' and im.getchannel('A').getextrema()==(255,255):
        rgb=im.convert('RGB')
        corners=[rgb.getpixel((0,0)),rgb.getpixel((rgb.width-1,0)),rgb.getpixel((0,rgb.height-1)),rgb.getpixel((rgb.width-1,rgb.height-1))]
        if all(sum(c)/3 > 242 for c in corners):
            px=im.load()
            for y in range(im.height):
                for x in range(im.width):
                    r,g,b,a=px[x,y]
                    if r>248 and g>248 and b>248:
                        px[x,y]=(255,255,255,0)
            bbox=im.getchannel('A').getbbox()
            if bbox: im=im.crop(bbox)
    maxw,maxh=460,210
    ratio=min(maxw/max(im.width,1),maxh/max(im.height,1))
    size=(max(1,int(im.width*ratio)),max(1,int(im.height*ratio)))
    im=im.resize(size,Image.Resampling.LANCZOS)
    out=Image.new('RGBA',CANVAS,(255,255,255,0))
    out.alpha_composite(im,((CANVAS[0]-size[0])//2,(CANVAS[1]-size[1])//2))
    return out


def save_under_limit(im: Image.Image, path: Path):
    # First full RGBA.
    b=io.BytesIO(); im.save(b,'PNG',optimize=True)
    data=b.getvalue()
    if len(data)<=MAX_BYTES:
        path.write_bytes(data); return len(data)
    # Palette fallback while preserving transparency.
    for colors in (256,192,128,96,64,48):
        q=im.quantize(colors=colors,method=Image.Quantize.FASTOCTREE)
        b=io.BytesIO(); q.save(b,'PNG',optimize=True)
        data=b.getvalue()
        if len(data)<=MAX_BYTES:
            path.write_bytes(data); return len(data)
    # Downsize if necessary.
    for factor in (0.9,0.8,0.7):
        small=im.resize((int(CANVAS[0]*factor),int(CANVAS[1]*factor)),Image.Resampling.LANCZOS)
        b=io.BytesIO(); small.save(b,'PNG',optimize=True)
        data=b.getvalue()
        if len(data)<=MAX_BYTES:
            path.write_bytes(data); return len(data)
    path.write_bytes(data); return len(data)


def placeholder(filename: str, display: str):
    # Only used for unresolved sources and clearly marked in manifest.
    im=Image.new('RGBA',CANVAS,(255,255,255,0))
    d=ImageDraw.Draw(im)
    font=ImageFont.load_default()
    d.rounded_rectangle((20,20,492,236),radius=20,outline=(130,130,130,255),width=3)
    text='UNRESOLVED\n'+display
    d.multiline_text((256,128),text,fill=(70,70,70,255),font=font,anchor='mm',align='center')
    return im


def make_preview(rows):
    items=[r for r in rows if r['status']!='UNRESOLVED']
    cols=5; tw,th=220,130; lh=30; pad=16
    nr=math.ceil(len(items)/cols)
    out=Image.new('RGB',(pad+cols*(tw+pad),pad+nr*(th+lh+pad)),(245,245,245))
    d=ImageDraw.Draw(out); font=ImageFont.load_default()
    for i,r in enumerate(items):
        rr,cc=divmod(i,cols); x=pad+cc*(tw+pad); y=pad+rr*(th+lh+pad)
        tile=Image.new('RGBA',(tw,th),(255,255,255,255))
        with Image.open(OUT/r['filename']) as im:
            im=im.convert('RGBA'); bbox=im.getchannel('A').getbbox() or (0,0,im.width,im.height); im=im.crop(bbox)
            ratio=min((tw-14)/max(im.width,1),(th-14)/max(im.height,1)); ns=(max(1,int(im.width*ratio)),max(1,int(im.height*ratio)))
            im=im.resize(ns,Image.Resampling.LANCZOS); tile.alpha_composite(im,((tw-ns[0])//2,(th-ns[1])//2))
        out.paste(tile.convert('RGB'),(x,y))
        label=r['filename'][:-4]
        box=d.textbbox((0,0),label,font=font); d.text((x+(tw-(box[2]-box[0]))/2,y+th+7),label,fill=(20,20,20),font=font)
    out.save(PREVIEW,'JPEG',quality=91,optimize=True)


def main():
    if OUT.exists():
        for p in OUT.iterdir(): p.unlink()
    else: OUT.mkdir()
    rows=[]
    for idx,(filename,display) in enumerate(ITEMS,1):
        print(f'[{idx}/{len(ITEMS)}] {display}',flush=True)
        c=choose(display)
        if not c:
            im=placeholder(filename,display); size=save_under_limit(im,OUT/filename)
            rows.append({'filename':filename,'title':display,'width':CANVAS[0],'height':CANVAS[1],'size_bytes':size,'size_kb':round(size/1024,2),'status':'UNRESOLVED','source_file':'','source_url':'','source_type':'','license':'','artist':'','score':''})
            continue
        try:
            media=req(c['media_url']).content
            im=normalize_image(media)
            size=save_under_limit(im,OUT/filename)
            status='OK' if size<=MAX_BYTES else 'TOO_LARGE'
            rows.append({'filename':filename,'title':display,'width':CANVAS[0],'height':CANVAS[1],'size_bytes':size,'size_kb':round(size/1024,2),'status':status,'source_file':c['file_title'],'source_url':c['description_url'] or c['media_url'],'source_type':c['api'],'license':c['license'],'artist':c['artist'],'score':c['score']})
            print('   ->',c['file_title'],'score',c['score'],round(size/1024,1),'KB',flush=True)
        except Exception as e:
            im=placeholder(filename,display); size=save_under_limit(im,OUT/filename)
            rows.append({'filename':filename,'title':display,'width':CANVAS[0],'height':CANVAS[1],'size_bytes':size,'size_kb':round(size/1024,2),'status':'UNRESOLVED','source_file':'','source_url':'','source_type':'','license':'','artist':'','score':'','notes':str(e)})
        time.sleep(0.35)
    fields=['filename','title','width','height','size_bytes','size_kb','status','source_file','source_url','source_type','license','artist','score']
    with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    unresolved=[r for r in rows if r['status']=='UNRESOLVED']
    if unresolved:
        (OUT/'UNRESOLVED.txt').write_text('\n'.join(f"{r['filename']}: {r['title']}" for r in unresolved)+'\n',encoding='utf-8')
    make_preview(rows)
    if ZIP.exists(): ZIP.unlink()
    with zipfile.ZipFile(ZIP,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.iterdir()): z.write(p,arcname=p.name)
        z.write(PREVIEW,arcname='preview.jpg')
    good=sum(r['status']=='OK' for r in rows)
    print(f'Created {good}/{len(rows)} OK logos; unresolved={len(unresolved)}')
    # Do not fail for unresolved; manifest makes them explicit.

if __name__=='__main__':
    main()
