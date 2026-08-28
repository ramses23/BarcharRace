from pathlib import Path
import csv, io, json, math, re, time, zipfile
import requests
from PIL import Image, ImageDraw, ImageFont
from rembg import remove

API = 'https://graphql.anilist.co'
UA = 'BarChartStudioAssetBuilder/1.0'
MAX_BYTES = 130 * 1024
CANVAS = 512
PAD = 26
OUT = Path('anime_primary_assets')
OUT.mkdir(exist_ok=True)
ZIP = Path('anime_primary_assets_png_max130kb.zip')
PREVIEW = Path('anime_primary_assets_preview.jpg')

ASSETS = [
('goku.png','Goku','Dragon Ball'),('vegeta.png','Vegeta','Dragon Ball'),('gohan.png','Gohan','Dragon Ball'),('piccolo.png','Piccolo','Dragon Ball'),('broly.png','Broly','Dragon Ball'),
('naruto_uzumaki.png','Naruto Uzumaki','Naruto'),('sasuke_uchiha.png','Sasuke Uchiha','Naruto'),('kakashi_hatake.png','Kakashi Hatake','Naruto'),('sakura_haruno.png','Sakura Haruno','Naruto'),
('monkey_d_luffy.png','Monkey D. Luffy','One Piece'),('roronoa_zoro.png','Roronoa Zoro','One Piece'),('nami.png','Nami','One Piece'),('sanji.png','Sanji','One Piece'),
('ichigo_kurosaki.png','Ichigo Kurosaki','Bleach'),('rukia_kuchiki.png','Rukia Kuchiki','Bleach'),('sailor_moon.png','Sailor Moon','Sailor Moon'),('astro_boy.png','Astro Boy','Astro Boy'),('doraemon.png','Doraemon','Doraemon'),
('ranma_saotome.png','Ranma Saotome','Ranma 1/2'),('inuyasha.png','Inuyasha','Inuyasha'),('kagome_higurashi.png','Kagome Higurashi','Inuyasha'),('yusuke_urameshi.png','Yusuke Urameshi','Yu Yu Hakusho'),
('gon_freecss.png','Gon Freecss','Hunter x Hunter'),('killua_zoldyck.png','Killua Zoldyck','Hunter x Hunter'),('shinji_ikari.png','Shinji Ikari','Neon Genesis Evangelion'),('rei_ayanami.png','Rei Ayanami','Neon Genesis Evangelion'),('asuka_langley.png','Asuka Langley Soryu','Neon Genesis Evangelion'),
('spike_spiegel.png','Spike Spiegel','Cowboy Bebop'),('edward_elric.png','Edward Elric','Fullmetal Alchemist'),('light_yagami.png','Light Yagami','Death Note'),('l_lawliet.png','L Lawliet','Death Note'),
('eren_yeager.png','Eren Yeager','Attack on Titan'),('mikasa_ackerman.png','Mikasa Ackerman','Attack on Titan'),('levi_ackerman.png','Levi Ackerman','Attack on Titan'),('saitama.png','Saitama','One-Punch Man'),
('tanjiro_kamado.png','Tanjiro Kamado','Demon Slayer'),('nezuko_kamado.png','Nezuko Kamado','Demon Slayer'),('zenitsu_agatsuma.png','Zenitsu Agatsuma','Demon Slayer'),
('satoru_gojo.png','Satoru Gojo','Jujutsu Kaisen'),('yuji_itadori.png','Yuji Itadori','Jujutsu Kaisen'),('megumi_fushiguro.png','Megumi Fushiguro','Jujutsu Kaisen'),
('denji.png','Denji','Chainsaw Man'),('makima.png','Makima','Chainsaw Man'),('power.png','Power','Chainsaw Man'),('frieren.png','Frieren','Frieren: Beyond Journey’s End'),('anya_forger.png','Anya Forger','Spy x Family'),
('shigeo_kageyama.png','Shigeo Kageyama','Mob Psycho 100'),('motoko_kusanagi.png','Motoko Kusanagi','Ghost in the Shell'),('kenshiro.png','Kenshiro','Fist of the North Star'),('pegasus_seiya.png','Pegasus Seiya','Saint Seiya'),
('ash_ketchum.png','Ash Ketchum','Pokémon'),('pikachu.png','Pikachu','Pokémon'),('vash_the_stampede.png','Vash the Stampede','Trigun'),('kenshin_himura.png','Kenshin Himura','Rurouni Kenshin'),
('jotaro_kujo.png','Jotaro Kujo','JoJo’s Bizarre Adventure'),('dio_brando.png','Dio Brando','JoJo’s Bizarre Adventure'),('lelouch.png','Lelouch Lamperouge','Code Geass'),('kirito.png','Kirito','Sword Art Online'),('subaru_natsuki.png','Subaru Natsuki','Re:Zero'),('rem_rezero.png','Rem','Re:Zero')]

ALIASES = {
'Ash Ketchum':'Satoshi', 'Sailor Moon':'Usagi Tsukino', 'Astro Boy':'Atom',
'Gohan':'Son Gohan','Goku':'Son Goku','Kirito':'Kazuto Kirigaya','L Lawliet':'L',
'Asuka Langley Soryu':'Asuka Langley Souryuu','Frieren':'Frieren','Dio Brando':'Dio Brando'
}

QUERY = '''query($search:String){Page(page:1,perPage:10){characters(search:$search,sort:[SEARCH_MATCH]){id name{full native alternative} image{large medium} siteUrl media(perPage:10){nodes{title{romaji english native}}}}}}'''

def norm(s):
    s = s or ''
    s = s.lower().replace('é','e').replace('’',"'").replace('×','x')
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def get_candidates(name):
    tries = [name]
    if name in ALIASES: tries.append(ALIASES[name])
    for term in tries:
        r = requests.post(API,json={'query':QUERY,'variables':{'search':term}},headers={'User-Agent':UA,'Accept':'application/json'},timeout=45)
        r.raise_for_status()
        data = r.json().get('data',{}).get('Page',{}).get('characters') or []
        if data: return data, term
    return [], tries[-1]

def score_candidate(c, requested, series):
    req, ser = norm(requested), norm(series)
    names = [c.get('name',{}).get('full'),c.get('name',{}).get('native')] + (c.get('name',{}).get('alternative') or [])
    nscore = max([100 if norm(n)==req else (70 if req in norm(n) or norm(n) in req else 0) for n in names if n] or [0])
    titles=[]
    for m in ((c.get('media') or {}).get('nodes') or []):
        t=m.get('title') or {}
        titles += [t.get('english'),t.get('romaji'),t.get('native')]
    sscore=max([60 if ser==norm(t) else (45 if ser in norm(t) or norm(t) in ser else 0) for t in titles if t] or [0])
    return nscore+sscore, [t for t in titles if t]

def download(url):
    r=requests.get(url,headers={'User-Agent':UA},timeout=45)
    r.raise_for_status()
    return r.content

def process_image(raw, out_path):
    src=Image.open(io.BytesIO(raw)).convert('RGBA')
    # Remove the background locally; rembg keeps non-human/cartoon silhouettes too.
    cut=remove(src).convert('RGBA')
    bbox=cut.getbbox()
    if not bbox: raise RuntimeError('background removal produced empty image')
    cut=cut.crop(bbox)
    max_side=CANVAS-2*PAD
    scale=min(max_side/cut.width,max_side/cut.height)
    nw=max(1,int(cut.width*scale)); nh=max(1,int(cut.height*scale))
    cut=cut.resize((nw,nh),Image.Resampling.LANCZOS)
    canvas=Image.new('RGBA',(CANVAS,CANVAS),(255,255,255,0))
    # Slight upward bias favors face/bust readability in circular BarChartStudio crops.
    x=(CANVAS-nw)//2
    y=max(PAD,(CANVAS-nh)//2-12)
    if y+nh>CANVAS-PAD: y=CANVAS-PAD-nh
    canvas.alpha_composite(cut,(x,y))
    # Quantize progressively to meet 130 KiB while preserving alpha.
    for colors in (256,192,160,128,96,80,64,48):
        q=canvas.quantize(colors=colors,method=Image.Quantize.FASTOCTREE)
        q.save(out_path,'PNG',optimize=True)
        if out_path.stat().st_size<=MAX_BYTES:
            return colors
    return colors

manifest=[]; search_report=[]; attribution=[]; ok_paths=[]
for idx,(filename,entity,series) in enumerate(ASSETS,1):
    print(f'[{idx}/{len(ASSETS)}] {entity} / {series}',flush=True)
    status='PENDING_NOT_FOUND'; notes=''; selected=''; titles=[]; query_used=''
    try:
        candidates, query_used = get_candidates(entity)
        scored=[]
        for c in candidates:
            sc, ts=score_candidate(c,entity,series); scored.append((sc,c,ts))
        scored.sort(key=lambda x:x[0],reverse=True)
        if not scored or scored[0][0] < 80:
            raise RuntimeError('No candidate passed identity/series score threshold')
        sc,c,titles=scored[0]
        selected=(c.get('image') or {}).get('large') or (c.get('image') or {}).get('medium')
        if not selected: raise RuntimeError('Selected character has no image URL')
        raw=download(selected)
        out=OUT/filename
        colors=process_image(raw,out)
        size=out.stat().st_size
        check=Image.open(out); check.verify()
        status='OK' if size<=MAX_BYTES else 'PENDING_LOW_QUALITY'
        if status=='OK': ok_paths.append(out)
        notes=f'AniList match score={sc}; palette={colors}; source media: ' + ' | '.join(titles[:4])
        manifest.append({'filename':filename,'entity':entity,'series':series,'entity_type':'fictional_character','role':'primary','status':status,'source_page_url':c.get('siteUrl') or '', 'direct_asset_url':selected,'source_type':'AniList character database','license_note':'Authentic franchise character image located via AniList; reuse rights not asserted.','width':CANVAS,'height':CANVAS,'size_bytes':size,'size_kb':round(size/1024,2),'background_removed':'yes','canvas':'512x512','notes':notes})
        attribution.append({'filename':filename,'entity':entity,'source_page_url':c.get('siteUrl') or '','author_or_owner':'Unknown / underlying rights holder','license':'Not specified by AniList','license_url':'','attribution_text':'Source URL retained for provenance.','rights_note':'Copyright/reuse rights not guaranteed.'})
    except Exception as e:
        notes=str(e)
        manifest.append({'filename':filename,'entity':entity,'series':series,'entity_type':'fictional_character','role':'primary','status':status,'source_page_url':'','direct_asset_url':selected,'source_type':'AniList character database','license_note':'','width':'','height':'','size_bytes':'','size_kb':'','background_removed':'','canvas':'512x512','notes':notes})
    search_report.append({'filename':filename,'entity':entity,'query':f'"{entity}" "{series}" authentic official character portrait; AniList search={query_used}','candidate_count':len(candidates) if 'candidates' in locals() else 0,'selected_source':selected,'selection_reason':'Best identity+series match; face/bust source image preferred','rejected_notes':notes if status!='OK' else ''})
    time.sleep(0.35)

fields=list(manifest[0].keys())
with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(manifest)
with (OUT/'SEARCH_REPORT.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=search_report[0].keys()); w.writeheader(); w.writerows(search_report)
with (OUT/'ASSET_ATTRIBUTION.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=attribution[0].keys() if attribution else ['filename']); w.writeheader(); w.writerows(attribution)

# Contact sheet
cols=5; thumb=150; labelh=30; gap=16; rows=math.ceil(len(ok_paths)/cols)
preview=Image.new('RGB',(gap+cols*(thumb+gap),gap+rows*(thumb+labelh+gap)),(245,245,245))
d=ImageDraw.Draw(preview)
try: font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
except: font=ImageFont.load_default()
for i,p in enumerate(ok_paths):
    r=i//cols;c=i%cols;x=gap+c*(thumb+gap);y=gap+r*(thumb+labelh+gap)
    tile=Image.new('RGBA',(thumb,thumb),(255,255,255,255)); im=Image.open(p).convert('RGBA'); im.thumbnail((thumb-8,thumb-8),Image.Resampling.LANCZOS); tile.alpha_composite(im,((thumb-im.width)//2,(thumb-im.height)//2)); preview.paste(tile.convert('RGB'),(x,y))
    label=p.stem[:20]; bb=d.textbbox((0,0),label,font=font); d.text((x+(thumb-(bb[2]-bb[0]))/2,y+thumb+5),label,fill=(25,25,25),font=font)
preview.save(PREVIEW,quality=92)

with zipfile.ZipFile(ZIP,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(OUT.iterdir()): z.write(p,arcname=p.name)
    z.write(PREVIEW,arcname='asset_pack_preview.jpg')

summary={'requested':len(ASSETS),'ok':sum(1 for r in manifest if r['status']=='OK'),'pending':sum(1 for r in manifest if r['status']!='OK'),'zip':str(ZIP)}
print(json.dumps(summary),flush=True)
if summary['ok']==0: raise SystemExit('No assets resolved')
