from __future__ import annotations

import csv, io, math, re, time, zipfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

OUT=Path('cartoon_logo_pack_v2')
ZIP=Path('cartoon_logos_png_max130kb.zip')
PREVIEW=Path('cartoon_logos_preview.jpg')
MAX_BYTES=130*1024
CANVAS=(512,256)
COMMONS='https://commons.wikimedia.org/w/api.php'
ENWIKI='https://en.wikipedia.org/w/api.php'
UA='BarcharRace-cartoon-logo-pack/2.0 (BarChartStudio; contact via GitHub ramses23/BarcharRace)'
S=requests.Session(); S.headers.update({'User-Agent':UA})

ITEMS=[
('adventure_time.png','Adventure Time'),('bugs_bunny.png','Bugs Bunny'),('ducktales.png','DuckTales'),('gumball.png','The Amazing World of Gumball'),('paw_patrol.png','PAW Patrol'),('regular_show.png','Regular Show'),('teen_titans_go.png','Teen Titans Go!'),('woody_woodpecker.png','Woody Woodpecker'),
('animaniacs.png','Animaniacs'),('cocomelon.png','CoComelon'),('ed_edd_n_eddy.png','Ed, Edd n Eddy'),('looney_tunes.png','Looney Tunes'),('peppa_pig.png','Peppa Pig'),('rick_and_morty.png','Rick and Morty'),('the_flintstones.png','The Flintstones'),('yogi_bear.png','Yogi Bear'),
('arthur.png','Arthur TV series'),('courage.png','Courage the Cowardly Dog'),('family_guy.png','Family Guy'),('masha_and_bear.png','Masha and the Bear'),('phineas_and_ferb.png','Phineas and Ferb'),('scooby_doo.png','Scooby-Doo'),('the_jetsons.png','The Jetsons'),
('avatar_last_airbender.png','Avatar The Last Airbender'),('dexters_laboratory.png',"Dexter's Laboratory"),('felix_the_cat.png','Felix the Cat'),('mickey_mouse.png','Mickey Mouse'),('pink_panther.png','The Pink Panther'),('south_park.png','South Park'),('the_simpsons.png','The Simpsons'),
('batman_tas.png','Batman The Animated Series'),('dora_explorer.png','Dora the Explorer'),('futurama.png','Futurama'),('miraculous_ladybug.png','Miraculous Ladybug'),('pokemon_tv.png','Pokémon anime'),('spongebob.png','SpongeBob SquarePants'),('tmnt.png','Teenage Mutant Ninja Turtles'),
('bluey.png','Bluey TV series'),('dragon_ball_z.png','Dragon Ball Z'),('gravity_falls.png','Gravity Falls'),('mlp_friendship.png','My Little Pony Friendship Is Magic'),('popeye.png','Popeye'),('steven_universe.png','Steven Universe'),('tom_and_jerry.png','Tom and Jerry')]

STOP={'the','a','an','and','tv','series','anime','of','my','is','go'}
BAD={'poster','screenshot','episode','dvd','cover','wallpaper','cosplay','costume','toy','plush','figurine','mural','stamp','coin','building','game cover','soundtrack'}

def norm(s):
    s=s.lower().replace('&',' and ')
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return ' '.join(s.split())

def score(title,display,mime,w,h):
    ft=norm(title.replace('File:','')); dn=norm(display); toks=[x for x in dn.split() if x not in STOP and len(x)>1]
    sc=0
    if 'logo' in ft: sc+=120
    if 'wordmark' in ft or 'logotype' in ft: sc+=80
    if 'title card' in ft or 'titlecard' in ft: sc+=50
    elif 'title' in ft: sc+=25
    m=sum(t in ft for t in toks); sc+=m*12
    if toks and m>=max(1,len(toks)-1): sc+=40
    if mime in ('image/png','image/svg+xml'): sc+=20
    if w>=500: sc+=8
    if w>=h: sc+=8
    for b in BAD:
        if b in ft: sc-=90
    return sc

def search_one(api,display,query):
    params={'action':'query','format':'json','generator':'search','gsrsearch':query,'gsrnamespace':6,'gsrlimit':15,'prop':'imageinfo','iiprop':'url|size|mime|extmetadata','iiurlwidth':1200}
    try:
        r=S.get(api,params=params,timeout=20); r.raise_for_status(); data=r.json()
    except Exception:
        return []
    out=[]
    for p in (data.get('query',{}).get('pages',{}) or {}).values():
        ii=(p.get('imageinfo') or [{}])[0]
        url=ii.get('thumburl') or ii.get('url')
        if not url: continue
        w=int(ii.get('thumbwidth') or ii.get('width') or 0); h=int(ii.get('thumbheight') or ii.get('height') or 0); mime=ii.get('mime',''); ext=ii.get('extmetadata') or {}
        out.append({'title':p.get('title',''),'url':url,'orig_url':ii.get('url') or url,'desc':ii.get('descriptionurl',''),'mime':mime,'width':w,'height':h,'license':(ext.get('LicenseShortName') or {}).get('value',''),'artist':re.sub('<[^>]+>',' ',(ext.get('Artist') or {}).get('value','')).strip(),'score':score(p.get('title',''),display,mime,w,h),'source':'commons' if 'commons.wikimedia' in api else 'enwiki'})
    return out

def find_candidate(display):
    queries=[f'{display} logo',f'{display} wordmark',f'{display} title']
    c=[]
    for q in queries:
        c.extend(search_one(COMMONS,display,q)); time.sleep(.12)
        c.extend(search_one(ENWIKI,display,q)); time.sleep(.12)
        if c and max(x['score'] for x in c)>=180: break
    # dedupe by title/source
    seen=set(); uniq=[]
    for x in c:
        k=(x['source'],x['title'])
        if k not in seen: seen.add(k); uniq.append(x)
    uniq.sort(key=lambda x:x['score'],reverse=True)
    return uniq[0] if uniq else None

def clean_url(url):
    # Wikimedia sometimes returns tracking query parameters; use the actual media URL without them.
    p=urlsplit(url); return urlunsplit((p.scheme,p.netloc,p.path,'',''))

def download_candidate(c):
    urls=[]
    for u in (c.get('url'),c.get('orig_url')):
        if u:
            u=clean_url(u)
            if u not in urls: urls.append(u)
    last=None
    for url in urls:
        for attempt in range(5):
            try:
                r=S.get(url,timeout=45)
                if r.status_code==429:
                    time.sleep(6+attempt*4); continue
                r.raise_for_status()
                if len(r.content)<200: raise RuntimeError('tiny payload')
                return r.content,url
            except Exception as e:
                last=e; time.sleep(2+attempt*2)
    raise RuntimeError(str(last))

def normalize(data):
    with Image.open(io.BytesIO(data)) as src: im=ImageOps.exif_transpose(src).convert('RGBA')
    box=im.getchannel('A').getbbox()
    if box: im=im.crop(box)
    # Remove only pure/near-pure white if four corners indicate a white background.
    if im.getchannel('A').getextrema()==(255,255) and im.width>1 and im.height>1:
        rgb=im.convert('RGB'); corners=[rgb.getpixel((0,0)),rgb.getpixel((rgb.width-1,0)),rgb.getpixel((0,rgb.height-1)),rgb.getpixel((rgb.width-1,rgb.height-1))]
        if all(min(c)>246 for c in corners):
            px=im.load()
            for y in range(im.height):
                for x in range(im.width):
                    r,g,b,a=px[x,y]
                    if r>250 and g>250 and b>250: px[x,y]=(255,255,255,0)
            box=im.getchannel('A').getbbox()
            if box: im=im.crop(box)
    ratio=min(462/max(1,im.width),212/max(1,im.height)); ns=(max(1,int(im.width*ratio)),max(1,int(im.height*ratio)))
    im=im.resize(ns,Image.Resampling.LANCZOS); out=Image.new('RGBA',CANVAS,(255,255,255,0)); out.alpha_composite(im,((512-ns[0])//2,(256-ns[1])//2)); return out

def save_limit(im,path):
    b=io.BytesIO(); im.save(b,'PNG',optimize=True); data=b.getvalue()
    if len(data)<=MAX_BYTES: path.write_bytes(data); return len(data)
    for colors in (256,192,128,96,64,48):
        q=im.quantize(colors=colors,method=Image.Quantize.FASTOCTREE); b=io.BytesIO(); q.save(b,'PNG',optimize=True); data=b.getvalue()
        if len(data)<=MAX_BYTES: path.write_bytes(data); return len(data)
    path.write_bytes(data); return len(data)

def unresolved(display):
    im=Image.new('RGBA',CANVAS,(255,255,255,0)); d=ImageDraw.Draw(im); d.rounded_rectangle((15,15,497,241),radius=20,outline=(125,125,125,255),width=3); d.multiline_text((256,128),'UNRESOLVED\n'+display,anchor='mm',align='center',fill=(70,70,70,255),font=ImageFont.load_default()); return im

def make_preview(rows):
    good=[r for r in rows if r['status']=='OK']; cols=5; tw,th,lh,pad=220,130,28,14; nr=math.ceil(len(good)/cols)
    out=Image.new('RGB',(pad+cols*(tw+pad),pad+nr*(th+lh+pad)),(245,245,245)); d=ImageDraw.Draw(out); font=ImageFont.load_default()
    for i,r in enumerate(good):
        rr,cc=divmod(i,cols); x=pad+cc*(tw+pad); y=pad+rr*(th+lh+pad); tile=Image.new('RGBA',(tw,th),(255,255,255,255))
        with Image.open(OUT/r['filename']) as im:
            im=im.convert('RGBA'); box=im.getchannel('A').getbbox() or (0,0,im.width,im.height); im=im.crop(box); ratio=min((tw-12)/im.width,(th-12)/im.height); ns=(max(1,int(im.width*ratio)),max(1,int(im.height*ratio))); im=im.resize(ns,Image.Resampling.LANCZOS); tile.alpha_composite(im,((tw-ns[0])//2,(th-ns[1])//2))
        out.paste(tile.convert('RGB'),(x,y)); lab=r['filename'][:-4]; bb=d.textbbox((0,0),lab,font=font); d.text((x+(tw-(bb[2]-bb[0]))/2,y+th+6),lab,fill=(20,20,20),font=font)
    out.save(PREVIEW,'JPEG',quality=91,optimize=True)

def main():
    OUT.mkdir(exist_ok=True)
    for p in OUT.iterdir(): p.unlink()
    rows=[]
    # Resolve metadata one-by-one to stay below MediaWiki rate limits.
    resolved=[]
    for i,(filename,display) in enumerate(ITEMS,1):
        print(f'[SEARCH {i}/{len(ITEMS)}] {display}',flush=True)
        c=find_candidate(display); resolved.append((filename,display,c));
        if c: print('  candidate:',c['title'],'score',c['score'],flush=True)
        else: print('  candidate: NONE',flush=True)
        time.sleep(.35)
    # Download sequentially with deliberate pacing to avoid upload.wikimedia 429 responses.
    for i,(filename,display,c) in enumerate(resolved,1):
        print(f'[DOWNLOAD {i}/{len(ITEMS)}] {display}',flush=True)
        if not c:
            size=save_limit(unresolved(display),OUT/filename); rows.append({'filename':filename,'title':display,'width':512,'height':256,'size_bytes':size,'size_kb':round(size/1024,2),'status':'UNRESOLVED','source_file':'','source_url':'','source_type':'','license':'','artist':'','score':'','notes':'no candidate'}); continue
        try:
            data,used=download_candidate(c); im=normalize(data); size=save_limit(im,OUT/filename); st='OK' if size<=MAX_BYTES else 'TOO_LARGE'; rows.append({'filename':filename,'title':display,'width':512,'height':256,'size_bytes':size,'size_kb':round(size/1024,2),'status':st,'source_file':c['title'],'source_url':c['desc'] or used,'source_type':c['source'],'license':c['license'],'artist':c['artist'],'score':c['score'],'notes':''}); print('  OK',round(size/1024,1),'KB',flush=True)
        except Exception as e:
            size=save_limit(unresolved(display),OUT/filename); rows.append({'filename':filename,'title':display,'width':512,'height':256,'size_bytes':size,'size_kb':round(size/1024,2),'status':'UNRESOLVED','source_file':c['title'],'source_url':c['desc'],'source_type':c['source'],'license':c['license'],'artist':c['artist'],'score':c['score'],'notes':str(e)}); print('  FAILED',e,flush=True)
        time.sleep(1.5)
    fields=['filename','title','width','height','size_bytes','size_kb','status','source_file','source_url','source_type','license','artist','score','notes']
    with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    missing=[r for r in rows if r['status']=='UNRESOLVED']
    if missing: (OUT/'UNRESOLVED.txt').write_text('\n'.join(f"{r['filename']}: {r['title']} | {r['notes']}" for r in missing)+'\n',encoding='utf-8')
    make_preview(rows)
    if ZIP.exists(): ZIP.unlink()
    with zipfile.ZipFile(ZIP,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.iterdir()): z.write(p,arcname=p.name)
        z.write(PREVIEW,arcname='preview.jpg')
    print('FINAL OK=',sum(r['status']=='OK' for r in rows),'UNRESOLVED=',len(missing),flush=True)

if __name__=='__main__': main()
