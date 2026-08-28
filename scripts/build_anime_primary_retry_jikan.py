from pathlib import Path
import csv, io, json, math, re, time, zipfile
import requests
from PIL import Image, ImageDraw, ImageFont
from rembg import remove

BASE='https://api.jikan.moe/v4'
UA='BarChartStudioAssetBuilder/1.0'
MAX_BYTES=130*1024; CANVAS=512; PAD=26
OUT=Path('anime_primary_retry_assets'); OUT.mkdir(exist_ok=True)
ZIP=Path('anime_primary_retry_assets_png_max130kb.zip'); PREVIEW=Path('anime_primary_retry_preview.jpg')
ASSETS=[
('light_yagami.png','Light Yagami','Death Note'),('l_lawliet.png','L Lawliet','Death Note'),('eren_yeager.png','Eren Yeager','Attack on Titan'),('mikasa_ackerman.png','Mikasa Ackerman','Attack on Titan'),('levi_ackerman.png','Levi Ackerman','Attack on Titan'),('saitama.png','Saitama','One-Punch Man'),('tanjiro_kamado.png','Tanjiro Kamado','Demon Slayer'),('nezuko_kamado.png','Nezuko Kamado','Demon Slayer'),('zenitsu_agatsuma.png','Zenitsu Agatsuma','Demon Slayer'),('satoru_gojo.png','Satoru Gojo','Jujutsu Kaisen'),('yuji_itadori.png','Yuji Itadori','Jujutsu Kaisen'),('megumi_fushiguro.png','Megumi Fushiguro','Jujutsu Kaisen'),('denji.png','Denji','Chainsaw Man'),('makima.png','Makima','Chainsaw Man'),('power.png','Power','Chainsaw Man'),('frieren.png','Frieren','Frieren: Beyond Journey’s End'),('anya_forger.png','Anya Forger','Spy x Family'),('shigeo_kageyama.png','Shigeo Kageyama','Mob Psycho 100'),('motoko_kusanagi.png','Motoko Kusanagi','Ghost in the Shell'),('kenshiro.png','Kenshiro','Fist of the North Star'),('pegasus_seiya.png','Pegasus Seiya','Saint Seiya'),('ash_ketchum.png','Ash Ketchum','Pokémon'),('pikachu.png','Pikachu','Pokémon'),('vash_the_stampede.png','Vash the Stampede','Trigun'),('kenshin_himura.png','Kenshin Himura','Rurouni Kenshin'),('jotaro_kujo.png','Jotaro Kujo','JoJo’s Bizarre Adventure'),('dio_brando.png','Dio Brando','JoJo’s Bizarre Adventure'),('lelouch.png','Lelouch Lamperouge','Code Geass'),('kirito.png','Kirito','Sword Art Online'),('subaru_natsuki.png','Subaru Natsuki','Re:Zero'),('rem_rezero.png','Rem','Re:Zero')]
ALIASES={'L Lawliet':'L','Ash Ketchum':'Satoshi','Satoru Gojo':'Satoru Gojou','Yuji Itadori':'Yuuji Itadori','Jotaro Kujo':'Joutarou Kuujou','Dio Brando':'Dio Brando','Motoko Kusanagi':'Motoko Kusanagi','Pegasus Seiya':'Seiya','Kirito':'Kazuto Kirigaya'}

def norm(s):
    s=(s or '').lower().replace('é','e').replace('’',"'").replace('×','x')
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def get_json(url,params=None,retries=6):
    for i in range(retries):
        r=requests.get(url,params=params,headers={'User-Agent':UA},timeout=45)
        if r.status_code==429:
            time.sleep(2.5*(i+1)); continue
        r.raise_for_status(); return r.json()
    raise RuntimeError('rate limited after retries')

def search(name):
    terms=[name]
    if name in ALIASES: terms.append(ALIASES[name])
    for term in terms:
        js=get_json(BASE+'/characters',{'q':term,'limit':10,'order_by':'favorites','sort':'desc'})
        data=js.get('data') or []
        if data: return data,term
        time.sleep(0.7)
    return [],terms[-1]

def full(cid):
    return (get_json(f'{BASE}/characters/{cid}/full').get('data') or {})

def score_name(c,requested):
    req=norm(requested); names=[c.get('name'),c.get('name_kanji')] + (c.get('nicknames') or [])
    vals=[]
    for n in names:
        if not n: continue
        nn=norm(n)
        vals.append(100 if nn==req else (80 if req in nn or nn in req else 0))
    return max(vals or [0])

def score_series(fc,series):
    ser=norm(series); best=0; titles=[]
    for a in fc.get('anime') or []:
        anime=a.get('anime') or {}; title=anime.get('title') or ''; titles.append(title)
        nt=norm(title)
        if ser==nt: best=max(best,70)
        elif ser in nt or nt in ser: best=max(best,55)
        else:
            # common franchise simplifications
            for token in ('dragon ball','naruto','one piece','bleach','death note','attack on titan','demon slayer','jujutsu kaisen','chainsaw man','frieren','spy x family','mob psycho','ghost in the shell','saint seiya','pokemon','trigun','rurouni kenshin','jojo','code geass','sword art online','re zero'):
                if token in ser and token in nt: best=max(best,50)
    return best,titles

def download(url):
    r=requests.get(url,headers={'User-Agent':UA},timeout=45); r.raise_for_status(); return r.content

def process(raw,out):
    src=Image.open(io.BytesIO(raw)).convert('RGBA'); cut=remove(src).convert('RGBA'); bbox=cut.getbbox()
    if not bbox: raise RuntimeError('empty cutout')
    cut=cut.crop(bbox); maxside=CANVAS-2*PAD; scale=min(maxside/cut.width,maxside/cut.height); nw=max(1,int(cut.width*scale)); nh=max(1,int(cut.height*scale)); cut=cut.resize((nw,nh),Image.Resampling.LANCZOS)
    canv=Image.new('RGBA',(CANVAS,CANVAS),(255,255,255,0)); x=(CANVAS-nw)//2; y=max(PAD,(CANVAS-nh)//2-12); y=min(y,CANVAS-PAD-nh); canv.alpha_composite(cut,(x,y))
    for colors in (256,192,160,128,96,80,64,48):
        q=canv.quantize(colors=colors,method=Image.Quantize.FASTOCTREE); q.save(out,'PNG',optimize=True)
        if out.stat().st_size<=MAX_BYTES: return colors
    return colors

manifest=[]; report=[]; attrib=[]; ok=[]
for idx,(filename,entity,series) in enumerate(ASSETS,1):
    print(f'[{idx}/{len(ASSETS)}] {entity}',flush=True); selected=''; qterm=''; candidates=[]; notes=''; status='PENDING_NOT_FOUND'
    try:
        candidates,qterm=search(entity); scored=[]
        # inspect a few strongest-name candidates and verify their animeography
        ranked=sorted(candidates,key=lambda c:score_name(c,entity),reverse=True)[:4]
        for c in ranked:
            ns=score_name(c,entity); fc=full(c['mal_id']); ss,titles=score_series(fc,series); scored.append((ns+ss,c,fc,titles,ns,ss)); time.sleep(0.75)
        scored.sort(key=lambda x:x[0],reverse=True)
        if not scored or scored[0][0]<100: raise RuntimeError('No Jikan candidate passed identity/series threshold')
        total,c,fc,titles,ns,ss=scored[0]
        imgs=(c.get('images') or {}).get('jpg') or {}; selected=imgs.get('image_url') or imgs.get('large_image_url')
        if not selected: raise RuntimeError('No selected image URL')
        raw=download(selected); out=OUT/filename; colors=process(raw,out); size=out.stat().st_size; Image.open(out).verify(); status='OK' if size<=MAX_BYTES else 'PENDING_LOW_QUALITY'
        if status=='OK': ok.append(out)
        notes=f'Jikan/MAL match score={total} (name={ns}, series={ss}); palette={colors}; animeography='+' | '.join(titles[:5])
        manifest.append({'filename':filename,'entity':entity,'series':series,'entity_type':'fictional_character','role':'primary','status':status,'source_page_url':c.get('url') or '', 'direct_asset_url':selected,'source_type':'MyAnimeList via Jikan API','license_note':'Authentic franchise character image indexed by MyAnimeList/Jikan; reuse rights not asserted.','width':CANVAS,'height':CANVAS,'size_bytes':size,'size_kb':round(size/1024,2),'background_removed':'yes','canvas':'512x512','notes':notes})
        attrib.append({'filename':filename,'entity':entity,'source_page_url':c.get('url') or '','author_or_owner':'Underlying franchise rights holder / source not specified','license':'Not specified','license_url':'','attribution_text':'Source URL retained for provenance.','rights_note':'Copyright/reuse rights not guaranteed.'})
    except Exception as e:
        notes=str(e); manifest.append({'filename':filename,'entity':entity,'series':series,'entity_type':'fictional_character','role':'primary','status':status,'source_page_url':'','direct_asset_url':selected,'source_type':'MyAnimeList via Jikan API','license_note':'','width':'','height':'','size_bytes':'','size_kb':'','background_removed':'','canvas':'512x512','notes':notes})
    report.append({'filename':filename,'entity':entity,'query':f'"{entity}" "{series}" authentic character portrait; Jikan q={qterm}','candidate_count':len(candidates),'selected_source':selected,'selection_reason':'Best exact-name candidate verified against animeography','rejected_notes':notes if status!='OK' else ''})
    time.sleep(1.0)

with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=manifest[0].keys());w.writeheader();w.writerows(manifest)
with (OUT/'SEARCH_REPORT.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=report[0].keys());w.writeheader();w.writerows(report)
with (OUT/'ASSET_ATTRIBUTION.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=attrib[0].keys() if attrib else ['filename']);w.writeheader();w.writerows(attrib)
cols=5;thumb=150;labelh=30;gap=16;rows=math.ceil(len(ok)/cols);prev=Image.new('RGB',(gap+cols*(thumb+gap),gap+rows*(thumb+labelh+gap)),(245,245,245));d=ImageDraw.Draw(prev)
try: font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
except: font=ImageFont.load_default()
for i,p in enumerate(ok):
    r=i//cols;c=i%cols;x=gap+c*(thumb+gap);y=gap+r*(thumb+labelh+gap);tile=Image.new('RGBA',(thumb,thumb),(255,255,255,255));im=Image.open(p).convert('RGBA');im.thumbnail((thumb-8,thumb-8),Image.Resampling.LANCZOS);tile.alpha_composite(im,((thumb-im.width)//2,(thumb-im.height)//2));prev.paste(tile.convert('RGB'),(x,y));lab=p.stem[:20];bb=d.textbbox((0,0),lab,font=font);d.text((x+(thumb-(bb[2]-bb[0]))/2,y+thumb+5),lab,fill=(25,25,25),font=font)
prev.save(PREVIEW,quality=92)
with zipfile.ZipFile(ZIP,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(OUT.iterdir()):z.write(p,arcname=p.name)
    z.write(PREVIEW,arcname='asset_pack_preview.jpg')
summary={'requested':len(ASSETS),'ok':sum(r['status']=='OK' for r in manifest),'pending':sum(r['status']!='OK' for r in manifest),'zip':str(ZIP)};print(json.dumps(summary),flush=True)
if summary['ok']==0: raise SystemExit('No assets resolved')
