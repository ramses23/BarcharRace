from __future__ import annotations

import csv, io, math, re, shutil, time, zipfile
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path('photo_pack_batch06_final')
ZIP_PATH = Path('football_player_photos_batch06_final_png_max130kb.zip')
MAX_BYTES = 130 * 1024
TARGET = 512
UA = {'User-Agent': 'Mozilla/5.0 BarcharRace-photo-pack/2.5'}
S = requests.Session(); S.headers.update(UA)

PLAYERS = [
 {'person':'Davor Šuker','file':'davor_uker.png','url':'https://hns.family/files/images/_resized/0000000775_616_400_cut.jpg','source':'Croatian Football Federation / HNS','license':'Official federation image; reuse terms not stated'},
 {'person':'Edin Džeko','file':'edin_d_eko.png','url':'https://www.nfsbih.ba/images/NOVE-SLIKE-A-REPREZENTATIVACA/edin-dzeko.jpg','source':'Football Association of Bosnia and Herzegovina','license':'Official federation image; reuse terms not stated'},
 {'person':'Gabino Sosa','file':'gabino_sosa.png','url':'https://www.centralcordoba.com.ar/resources/themes/default/images/historia/idolos/sosa-gabino.jpg','source':'Club Atlético Central Córdoba official history','license':'Official club historical image; reuse terms not stated'},
 {'person':'Gheorghe Hagi','file':'gheorghe_hagi.png','url':'https://www.ro.biography.name/images/sportivi/romania/gheorghe-hagi.jpg','source':'Biography.name','license':'License not stated'},
 {'person':'Héctor Scarone','file':'h_ctor_scarone.png','url':'https://estaticos-cdn.prensaiberica.es/clip/cb7ade19-cca8-46c8-af20-dcbe731c2ca0_alta-libre-aspect-ratio_default_0.jpg','source':'Sport / Prensa Ibérica','license':'Editorial image; license not stated'},
 {'person':'Hernando Salazar','file':'hernando_salazar.png','page':'https://www.besoccer.com/player/hernando-salazar-909307','source':'BeSoccer player profile','license':'License not stated'},
 {'person':'Isidro Lángara','file':'isidro_l_ngara.png','url':'https://statics-maker.llt-services.com/ovi/images/2022/12/14/xlarge/6267c58a-b01c-4e81-8942-abecf3ebf449.jpg','source':'Real Oviedo official website','license':'Official club historical image; reuse terms not stated'},
 {'person':'Joachim Streich','file':'joachim_streich.png','url':'https://s.hs-data.com/bilder/spieler/gross/17454.jpg','source':'WorldFootball.net / HEIM:SPIEL','license':'License not stated'},
 {'person':'José Pérez','file':'jos_p_rez.png','url':'https://cdn.conmebol.com/wp-content/uploads/2014/12/uruguay-1917.jpg','source':'CONMEBOL historical gallery — Uruguay 1917','license':'Official historical gallery; reuse terms not stated','selector':'top_second'},
 {'person':'Julio Libonatti','file':'julio_libonatti.png','url':'https://cdn.conmebol.com/wp-content/uploads/2015/05/julio-libonatti_0.jpg','source':'CONMEBOL historical gallery','license':'Official historical gallery; reuse terms not stated'},
 {'person':'Mahmoud Mokhtar El-Tetsh','file':'mahmoud_mokhtar_el_tetsh.png','url':'https://olympedia-photos.s3.us-east-1.amazonaws.com/24794.jpg','source':'Olympedia','license':'License not stated'},
 {'person':'Max Abegglen','file':'max_abegglen.png','url':'https://production-livingdocs-bluewin-ch.imgix.net/2020/8/25/d17fa4ef-27e2-4691-a17f-0d6d81484475.jpeg?crop=faces&fit=crop&h=630&w=1200','source':'blue News','license':'Editorial image; license not stated'},
 {'person':'Oldřich Nejedlý','file':'old_ich_nejedl.png','url':'https://www.fotbal.cz/files/images/2462/oldrich-nejedly-titulni.png','source':'Football Association of the Czech Republic (fotbal.cz)','license':'Official federation historical image; reuse terms not stated'},
 {'person':'Pelé','file':'pel.png','url':'https://www.ogol.com.br/img/jogadores/new/57/33/5733_pele_20250727230551.jpg','source':'oGol','license':'License not stated'},
 {'person':'Robert Lewandowski','file':'robert_lewandowski.png','url':'https://glos.live/content/other/clanek/2025_09/24676-robert.jpg','source':'PZPN promotional portrait via glos.live','license':'Official federation promotional image; reuse terms not stated'},
 {'person':'Ronaldo Nazário','file':'ronaldo.png','url':'https://www.leballonrond.fr/img/jogadores/new/10/22/1022_ronaldo_20241012221007.jpg','source':'Le Ballon Rond','license':'License not stated'},
 {'person':'Severino Varela','file':'severino_varela.png','url':'https://commons.wikimedia.org/wiki/Special:Redirect/file/Sevarela.jpg?width=800','source':'Wikimedia Commons — Sevarela.jpg','license':'Public domain (Argentina)'},
 {'person':'Toni Polster','file':'toni_polster.png','url':'https://primary.jwwb.nl/public/s/m/q/temp-qjzgnvqqhfxelgdladus/96a-13.png','source':'Micha’s 1.FC Köln site','license':'License not stated'},
]


def get(url, attempts=5):
    last=None
    for i in range(attempts):
        try:
            r=S.get(url,timeout=60,allow_redirects=True)
            if r.status_code==429:
                raise RuntimeError('429 rate limit')
            r.raise_for_status()
            return r
        except Exception as e:
            last=e; time.sleep(min(2**i,12))
    raise RuntimeError(f'GET failed: {url}: {last}')


def resolve_page_image(page):
    html=get(page).text
    patterns=[
      r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
      r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
      r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
    ]
    for p in patterns:
        m=re.search(p,html,re.I)
        if m:
            return m.group(1).replace('&amp;','&')
    # Fallback: player-related image URLs
    candidates=re.findall(r'https?://[^"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^"\']*)?',html,re.I)
    for u in candidates:
        if any(k in u.lower() for k in ['player','salazar','photo','image']): return u
    if candidates: return candidates[0]
    raise RuntimeError('No page image found')


def face_boxes(im):
    arr=np.array(im.convert('RGB')); gray=cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)
    cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    return cascade.detectMultiScale(gray,scaleFactor=1.06,minNeighbors=4,minSize=(25,25))


def crop_face(im, selector=None):
    im=ImageOps.exif_transpose(im).convert('RGB'); w,h=im.size
    faces=list(face_boxes(im))
    chosen=None
    if faces:
        if selector=='top_second':
            # Uruguay 1917: José Pérez is second standing player from the left.
            tops=[f for f in faces if f[1]+f[3]/2 < h*0.62]
            tops=sorted(tops,key=lambda f:f[0])
            if len(tops)>=2: chosen=tops[1]
        if chosen is None:
            chosen=max(faces,key=lambda f:int(f[2])*int(f[3]))
    if chosen is not None:
        x,y,fw,fh=[float(v) for v in chosen]; cx=x+fw/2; cy=y+fh/2
        side=min(max(fw*3.2,fh*3.5),max(w,h)); left=cx-side/2; top=cy-side*0.44
        box=(int(left),int(top),int(left+side),int(top+side))
        # clamp while keeping approximate square
        l,t,r,b=box
        if l<0:r-=l;l=0
        if t<0:b-=t;t=0
        if r>w:l-=r-w;r=w
        if b>h:t-=b-h;b=h
        cr=im.crop((max(0,l),max(0,t),min(w,r),min(h,b)))
        return ImageOps.fit(cr,(TARGET,TARGET),method=Image.Resampling.LANCZOS,centering=(.5,.45)),True
    return ImageOps.fit(im,(TARGET,TARGET),method=Image.Resampling.LANCZOS,centering=(.5,.35)),False


def save_png(im,path):
    best=None
    for side in (512,448,384,320,288):
        x=im if im.size==(side,side) else im.resize((side,side),Image.Resampling.LANCZOS)
        for colors in (192,128,96,64,48):
            q=x.quantize(colors=colors,method=Image.Quantize.MEDIANCUT)
            b=io.BytesIO(); q.save(b,'PNG',optimize=True); data=b.getvalue()
            if best is None or len(data)<len(best[0]): best=(data,side)
            if len(data)<=MAX_BYTES:
                path.write_bytes(data); return side,len(data)
    path.write_bytes(best[0]); return best[1],len(best[0])


def make_preview(rows):
    cols=5; card=180; label=34; pad=12; nr=math.ceil(len(rows)/cols)
    out=Image.new('RGB',(pad+cols*(card+pad),pad+nr*(card+label+pad)),'#f2f2f2')
    d=ImageDraw.Draw(out); font=ImageFont.load_default()
    for i,row in enumerate(rows):
        rr,cc=divmod(i,cols); x=pad+cc*(card+pad); y=pad+rr*(card+label+pad)
        with Image.open(ROOT/row['filename']) as im:
            tile=ImageOps.fit(im.convert('RGB'),(card,card),method=Image.Resampling.LANCZOS)
        out.paste(tile,(x,y)); d.text((x,y+card+6),row['filename'][:-4][:27],fill='#111',font=font)
    out.save(ROOT/'preview.jpg','JPEG',quality=90,optimize=True)


def main():
    if ROOT.exists(): shutil.rmtree(ROOT)
    ROOT.mkdir(); rows=[]; failures=[]
    for p in PLAYERS:
        print('Downloading',p['person'],flush=True)
        try:
            url=p.get('url') or resolve_page_image(p['page'])
            r=get(url)
            with Image.open(io.BytesIO(r.content)) as im:
                proc,face=crop_face(im,p.get('selector'))
            side,size=save_png(proc,ROOT/p['file'])
            rows.append({'filename':p['file'],'person_name':p['person'],'width':side,'height':side,'size_bytes':size,'size_kb':round(size/1024,2),'status':'OK','face_detected':'yes' if face else 'no','source_url':p.get('page') or url,'source_type':p['source'],'license_note':p['license'],'notes':'direct curated source'})
            print('OK',p['file'],round(size/1024,1),'KB face=',face,flush=True)
        except Exception as e:
            failures.append(f"{p['person']}: {type(e).__name__}: {e}"); print('FAILED',failures[-1],flush=True)
        time.sleep(1.0)
    fields=['filename','person_name','width','height','size_bytes','size_kb','status','face_detected','source_url','source_type','license_note','notes']
    rows.append({'filename':'na.png','person_name':'na','width':'','height':'','size_bytes':'','size_kb':'','status':'AMBIGUOUS_INPUT','face_detected':'','source_url':'','source_type':'','license_note':'','notes':"Filename 'na' does not uniquely identify a footballer; no image created to avoid a wrong identity."})
    with (ROOT/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    if failures:(ROOT/'DOWNLOAD_FAILURES.txt').write_text('\n'.join(failures)+'\n',encoding='utf-8')
    (ROOT/'UNRESOLVED_na.txt').write_text("The filename 'na' is ambiguous. No player image was guessed.\n",encoding='utf-8')
    good=[r for r in rows if r['status']=='OK']
    if good: make_preview(good)
    if ZIP_PATH.exists(): ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted(ROOT.iterdir()): z.write(f,arcname=f.name)
    print(f'Created {len(good)}/{len(PLAYERS)} resolved assets')
    if len(good) != len(PLAYERS):
        raise SystemExit(2)

if __name__=='__main__': main()
