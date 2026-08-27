from __future__ import annotations

import csv, io, math, re, time, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

OUT=Path('cartoon_logo_pack_fast')
ZIP=Path('cartoon_logos_png_max130kb.zip')
PREVIEW=Path('cartoon_logos_preview.jpg')
MAX_BYTES=130*1024
CANVAS=(512,256)
COMMONS='https://commons.wikimedia.org/w/api.php'
ENWIKI='https://en.wikipedia.org/w/api.php'
UA='BarcharRace-cartoon-logo-pack/1.1 (BarChartStudio)'

ITEMS=[
('adventure_time.png','Adventure Time'),('bugs_bunny.png','Bugs Bunny'),('ducktales.png','DuckTales'),('gumball.png','The Amazing World of Gumball'),('paw_patrol.png','PAW Patrol'),('regular_show.png','Regular Show'),('teen_titans_go.png','Teen Titans Go!'),('woody_woodpecker.png','Woody Woodpecker'),
('animaniacs.png','Animaniacs'),('cocomelon.png','CoComelon'),('ed_edd_n_eddy.png','Ed, Edd n Eddy'),('looney_tunes.png','Looney Tunes'),('peppa_pig.png','Peppa Pig'),('rick_and_morty.png','Rick and Morty'),('the_flintstones.png','The Flintstones'),('yogi_bear.png','Yogi Bear'),
('arthur.png','Arthur TV series'),('courage.png','Courage the Cowardly Dog'),('family_guy.png','Family Guy'),('masha_and_bear.png','Masha and the Bear'),('phineas_and_ferb.png','Phineas and Ferb'),('scooby_doo.png','Scooby-Doo'),('the_jetsons.png','The Jetsons'),
('avatar_last_airbender.png','Avatar The Last Airbender'),('dexters_laboratory.png',"Dexter's Laboratory"),('felix_the_cat.png','Felix the Cat'),('mickey_mouse.png','Mickey Mouse'),('pink_panther.png','The Pink Panther'),('south_park.png','South Park'),('the_simpsons.png','The Simpsons'),
('batman_tas.png','Batman The Animated Series'),('dora_explorer.png','Dora the Explorer'),('futurama.png','Futurama'),('miraculous_ladybug.png','Miraculous Ladybug'),('pokemon_tv.png','Pokémon anime'),('spongebob.png','SpongeBob SquarePants'),('tmnt.png','Teenage Mutant Ninja Turtles'),
('bluey.png','Bluey TV series'),('dragon_ball_z.png','Dragon Ball Z'),('gravity_falls.png','Gravity Falls'),('mlp_friendship.png','My Little Pony Friendship Is Magic'),('popeye.png','Popeye'),('steven_universe.png','Steven Universe'),('tom_and_jerry.png','Tom and Jerry')]

STOP={'the','a','an','and','tv','series','anime','of','my','is'}
BAD={'poster','screenshot','episode','dvd','cover','wallpaper','cosplay','costume','toy','plush','figurine','mural','stamp','coin','building','character model','game cover'}

def norm(s):
    s=s.lower().replace('&',' and ')
    s=re.sub(r'[^a-z0-9]+',' ',s)
    return ' '.join(s.split())

def score(title,display,mime,w,h):
    ft=norm(title.replace('File:','')); dn=norm(display); tok=[x for x in dn.split() if x not in STOP and len(x)>1]
    sc=0
    if 'logo' in ft: sc+=100
    if 'wordmark' in ft or 'logotype' in ft: sc+=70
    if 'title card' in ft or 'titlecard' in ft: sc+=45
    elif 'title' in ft: sc+=25
    m=sum(t in ft for t in tok); sc+=m*11
    if tok and m>=max(1,len(tok)-1): sc+=35
    if mime in ('image/png','image/svg+xml'): sc+=15
    if w>=500: sc+=8
    if w>=h: sc+=7
    for b in BAD:
        if b in ft: sc-=80
    return sc

def api_candidates(api,display):
    s=requests.Session(); s.headers['User-Agent']=UA
    q=f'"{display}" logo'
    try:
        r=s.get(api,params={'action':'query','format':'json','generator':'search','gsrsearch':q,'gsrnamespace':6,'gsrlimit':10,'prop':'imageinfo','iiprop':'url|size|mime|extmetadata','iiurlwidth':1400},timeout=15)
        r.raise_for_status(); data=r.json()
    except Exception:
        return []
    out=[]
    for p in (data.get('query',{}).get('pages',{}) or {}).values():
        ii=(p.get('imageinfo') or [{}])[0]; url=ii.get('thumburl') or ii.get('url')
        if not url: continue
        ext=ii.get('extmetadata') or {}; w=int(ii.get('thumbwidth') or ii.get('width') or 0); h=int(ii.get('thumbheight') or ii.get('height') or 0); mime=ii.get('mime','')
        out.append({'title':p.get('title',''),'url':url,'desc':ii.get('descriptionurl',''),'mime':mime,'width':w,'height':h,'license':(ext.get('LicenseShortName') or {}).get('value',''),'artist':re.sub('<[^>]+>',' ',(ext.get('Artist') or {}).get('value','')).strip(),'score':score(p.get('title',''),display,mime,w,h),'source':'commons' if 'commons' in api else 'enwiki'})
    return out

def find_candidate(display):
    cand=api_candidates(ENWIKI,display)+api_candidates(COMMONS,display)
    cand.sort(key=lambda x:x['score'],reverse=True)
    return cand[0] if cand else None

def download(url):
    s=requests.Session(); s.headers['User-Agent']=UA
    r=s.get(url,timeout=20); r.raise_for_status(); return r.content

def normalize(data):
    with Image.open(io.BytesIO(data)) as src:
        im=ImageOps.exif_transpose(src).convert('RGBA')
    # crop transparent bounds
    bbox=im.getchannel('A').getbbox();
    if bbox: im=im.crop(bbox)
    # conservative white background removal when all four corners are near-white
    if im.getchannel('A').getextrema()==(255,255):
        rgb=im.convert('RGB'); cor=[rgb.getpixel((0,0)),rgb.getpixel((rgb.width-1,0)),rgb.getpixel((0,rgb.height-1)),rgb.getpixel((rgb.width-1,rgb.height-1))]
        if all(min(c)>245 for c in cor):
            arr=im.load()
            for y in range(im.height):
                for x in range(im.width):
                    r,g,b,a=arr[x,y]
                    if r>250 and g>250 and b>250: arr[x,y]=(255,255,255,0)
            bbox=im.getchannel('A').getbbox();
            if bbox: im=im.crop(bbox)
    ratio=min(462/max(1,im.width),212/max(1,im.height)); ns=(max(1,int(im.width*ratio)),max(1,int(im.height*ratio)))
    im=im.resize(ns,Image.Resampling.LANCZOS)
    out=Image.new('RGBA',CANVAS,(255,255,255,0)); out.alpha_composite(im,((512-ns[0])//2,(256-ns[1])//2)); return out

def save_limit(im,path):
    b=io.BytesIO(); im.save(b,'PNG',optimize=True); data=b.getvalue()
    if len(data)<=MAX_BYTES: path.write_bytes(data); return len(data)
    for colors in (256,192,128,96,64):
        q=im.quantize(colors=colors,method=Image.Quantize.FASTOCTREE); b=io.BytesIO(); q.save(b,'PNG',optimize=True); data=b.getvalue()
        if len(data)<=MAX_BYTES: path.write_bytes(data); return len(data)
    path.write_bytes(data); return len(data)

def unresolved_image(display):
    im=Image.new('RGBA',CANVAS,(255,255,255,0)); d=ImageDraw.Draw(im); d.rounded_rectangle((15,15,497,241),radius=20,outline=(120,120,120,255),width=3); d.multiline_text((256,128),'UNRESOLVED\n'+display,anchor='mm',align='center',fill=(60,60,60,255),font=ImageFont.load_default()); return im

def work(item):
    filename,display=item; c=find_candidate(display)
    if not c: return filename,display,None,None,'no candidate'
    try:
        im=normalize(download(c['url'])); return filename,display,c,im,''
    except Exception as e: return filename,display,c,None,str(e)

def preview(rows):
    good=[r for r in rows if r['status']=='OK']; cols=5; tw,th,lh,pad=220,130,28,14; nr=math.ceil(len(good)/cols)
    out=Image.new('RGB',(pad+cols*(tw+pad),pad+nr*(th+lh+pad)),(245,245,245)); d=ImageDraw.Draw(out); font=ImageFont.load_default()
    for i,r in enumerate(good):
        rr,cc=divmod(i,cols); x=pad+cc*(tw+pad); y=pad+rr*(th+lh+pad); tile=Image.new('RGBA',(tw,th),(255,255,255,255))
        with Image.open(OUT/r['filename']) as im:
            im=im.convert('RGBA'); box=im.getchannel('A').getbbox() or (0,0,im.width,im.height); im=im.crop(box); ratio=min((tw-12)/im.width,(th-12)/im.height); ns=(max(1,int(im.width*ratio)),max(1,int(im.height*ratio))); im=im.resize(ns,Image.Resampling.LANCZOS); tile.alpha_composite(im,((tw-ns[0])//2,(th-ns[1])//2))
        out.paste(tile.convert('RGB'),(x,y)); lab=r['filename'][:-4]; bb=d.textbbox((0,0),lab,font=font); d.text((x+(tw-(bb[2]-bb[0]))/2,y+th+6),lab,fill=(20,20,20),font=font)
    out.save(PREVIEW,'JPEG',quality=90,optimize=True)

def main():
    OUT.mkdir(exist_ok=True)
    for p in OUT.iterdir(): p.unlink()
    results=[]
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs={ex.submit(work,item):item for item in ITEMS}
        for i,f in enumerate(as_completed(futs),1):
            filename,display,c,im,err=f.result(); print(f'[{i}/{len(ITEMS)}] {display}',flush=True)
            if im is None:
                size=save_limit(unresolved_image(display),OUT/filename); results.append({'filename':filename,'title':display,'width':512,'height':256,'size_bytes':size,'size_kb':round(size/1024,2),'status':'UNRESOLVED','source_file':c['title'] if c else '','source_url':c['desc'] if c else '','source_type':c['source'] if c else '','license':c['license'] if c else '','artist':c['artist'] if c else '','score':c['score'] if c else '','notes':err}); continue
            size=save_limit(im,OUT/filename); status='OK' if size<=MAX_BYTES else 'TOO_LARGE'; results.append({'filename':filename,'title':display,'width':512,'height':256,'size_bytes':size,'size_kb':round(size/1024,2),'status':status,'source_file':c['title'],'source_url':c['desc'] or c['url'],'source_type':c['source'],'license':c['license'],'artist':c['artist'],'score':c['score'],'notes':''}); print('  ->',c['title'],'score',c['score'],round(size/1024,1),'KB',flush=True)
    order={fn:i for i,(fn,_) in enumerate(ITEMS)}; results.sort(key=lambda r:order[r['filename']])
    fields=['filename','title','width','height','size_bytes','size_kb','status','source_file','source_url','source_type','license','artist','score','notes']
    with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(results)
    unresolved=[r for r in results if r['status']=='UNRESOLVED']
    if unresolved: (OUT/'UNRESOLVED.txt').write_text('\n'.join(f"{r['filename']}: {r['title']}" for r in unresolved)+'\n',encoding='utf-8')
    preview(results)
    if ZIP.exists(): ZIP.unlink()
    with zipfile.ZipFile(ZIP,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.iterdir()): z.write(p,arcname=p.name)
        z.write(PREVIEW,arcname='preview.jpg')
    print('OK',sum(r['status']=='OK' for r in results),'UNRESOLVED',len(unresolved),flush=True)

if __name__=='__main__': main()
