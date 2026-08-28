from pathlib import Path
import csv, io, json, math, re, time, zipfile
import requests
from PIL import Image, ImageDraw, ImageFont
from rembg import remove

API='https://graphql.anilist.co'; UA='BarChartStudioAssetBuilder/1.0'; MAX_BYTES=130*1024; CANVAS=512; PAD=26
OUT=Path('anime_primary_retry2_assets'); OUT.mkdir(exist_ok=True)
ZIP=Path('anime_primary_retry2_assets_png_max130kb.zip'); PREVIEW=Path('anime_primary_retry2_preview.jpg')
ASSETS=[
('light_yagami.png','Light Yagami','Death Note','Light Yagami'),('l_lawliet.png','L Lawliet','Death Note','L'),('eren_yeager.png','Eren Yeager','Attack on Titan','Eren Yeager'),('mikasa_ackerman.png','Mikasa Ackerman','Attack on Titan','Mikasa Ackerman'),('levi_ackerman.png','Levi Ackerman','Attack on Titan','Levi Ackerman'),('saitama.png','Saitama','One-Punch Man','Saitama'),('tanjiro_kamado.png','Tanjiro Kamado','Demon Slayer','Tanjirou Kamado'),('nezuko_kamado.png','Nezuko Kamado','Demon Slayer','Nezuko Kamado'),('zenitsu_agatsuma.png','Zenitsu Agatsuma','Demon Slayer','Zenitsu Agatsuma'),('satoru_gojo.png','Satoru Gojo','Jujutsu Kaisen','Satoru Gojou'),('yuji_itadori.png','Yuji Itadori','Jujutsu Kaisen','Yuuji Itadori'),('megumi_fushiguro.png','Megumi Fushiguro','Jujutsu Kaisen','Megumi Fushiguro'),('denji.png','Denji','Chainsaw Man','Denji'),('makima.png','Makima','Chainsaw Man','Makima'),('power.png','Power','Chainsaw Man','Power'),('frieren.png','Frieren','Frieren: Beyond Journey’s End','Frieren'),('anya_forger.png','Anya Forger','Spy x Family','Anya Forger'),('shigeo_kageyama.png','Shigeo Kageyama','Mob Psycho 100','Shigeo Kageyama'),('motoko_kusanagi.png','Motoko Kusanagi','Ghost in the Shell','Motoko Kusanagi'),('kenshiro.png','Kenshiro','Fist of the North Star','Kenshirou'),('pegasus_seiya.png','Pegasus Seiya','Saint Seiya','Seiya'),('ash_ketchum.png','Ash Ketchum','Pokémon','Satoshi'),('pikachu.png','Pikachu','Pokémon','Pikachu'),('vash_the_stampede.png','Vash the Stampede','Trigun','Vash the Stampede'),('kenshin_himura.png','Kenshin Himura','Rurouni Kenshin','Kenshin Himura'),('jotaro_kujo.png','Jotaro Kujo','JoJo’s Bizarre Adventure','Joutarou Kuujou'),('dio_brando.png','Dio Brando','JoJo’s Bizarre Adventure','Dio Brando'),('lelouch.png','Lelouch Lamperouge','Code Geass','Lelouch Lamperouge'),('kirito.png','Kirito','Sword Art Online','Kazuto Kirigaya'),('subaru_natsuki.png','Subaru Natsuki','Re:Zero','Subaru Natsuki'),('rem_rezero.png','Rem','Re:Zero','Rem')]

def esc(s): return s.replace('\\','\\\\').replace('"','\\"')
fields=[]
for i,(_,_,_,search) in enumerate(ASSETS):
    fields.append(f'''c{i}: Character(search:"{esc(search)}"){{id name{{full native alternative}} image{{large medium}} siteUrl media(perPage:10){{nodes{{title{{romaji english native}}}}}}}}''')
QUERY='query{'+ '\n'.join(fields) +'}'

def norm(s):
    s=(s or '').lower().replace('é','e').replace('’',"'").replace('×','x')
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def franchise_ok(series,titles):
    ser=norm(series)
    if not titles: return False
    for t in titles:
        nt=norm(t)
        if ser==nt or ser in nt or nt in ser: return True
        groups=[('demon slayer',['kimetsu no yaiba']),('attack on titan',['shingeki no kyojin']),('one punch man',['one punch man']),('spy x family',['spy x family']),('pokemon',['pokemon','pocket monsters']),('jojo s bizarre adventure',['jojo','jojo no kimyou na bouken']),('re zero',['re zero','rezero','re zero kara hajimeru']),('frieren beyond journey s end',['frieren','sousou no frieren']),('rurouni kenshin',['rurouni kenshin','samurai x']),('saint seiya',['saint seiya']),('ghost in the shell',['ghost in the shell']),('mob psycho 100',['mob psycho']),('jujutsu kaisen',['jujutsu kaisen']),('chainsaw man',['chainsaw man']),('code geass',['code geass']),('sword art online',['sword art online']),('trigun',['trigun']),('death note',['death note'])]
        for canonical,alts in groups:
            if canonical in ser and any(a in nt for a in alts): return True
    return False

def process(raw,out):
    src=Image.open(io.BytesIO(raw)).convert('RGBA'); cut=remove(src).convert('RGBA'); bbox=cut.getbbox()
    if not bbox: raise RuntimeError('empty cutout')
    cut=cut.crop(bbox); maxside=CANVAS-2*PAD; scale=min(maxside/cut.width,maxside/cut.height); nw=max(1,int(cut.width*scale)); nh=max(1,int(cut.height*scale)); cut=cut.resize((nw,nh),Image.Resampling.LANCZOS)
    canv=Image.new('RGBA',(CANVAS,CANVAS),(255,255,255,0)); x=(CANVAS-nw)//2; y=max(PAD,(CANVAS-nh)//2-12); y=min(y,CANVAS-PAD-nh); canv.alpha_composite(cut,(x,y))
    for colors in (256,192,160,128,96,80,64,48):
        q=canv.quantize(colors=colors,method=Image.Quantize.FASTOCTREE); q.save(out,'PNG',optimize=True)
        if out.stat().st_size<=MAX_BYTES: return colors
    return colors

r=requests.post(API,json={'query':QUERY},headers={'User-Agent':UA,'Accept':'application/json','Content-Type':'application/json'},timeout=90)
r.raise_for_status(); payload=r.json()
if payload.get('errors'): print('GraphQL partial errors:',payload['errors'],flush=True)
data=payload.get('data') or {}
manifest=[]; report=[]; attrib=[]; ok=[]
for i,(filename,entity,series,search) in enumerate(ASSETS):
    c=data.get(f'c{i}'); selected=''; status='PENDING_NOT_FOUND'; notes=''; titles=[]
    try:
        if not c: raise RuntimeError('AniList returned no character')
        for m in ((c.get('media') or {}).get('nodes') or []):
            t=m.get('title') or {}; titles += [x for x in (t.get('english'),t.get('romaji'),t.get('native')) if x]
        if not franchise_ok(series,titles): raise RuntimeError('Character result did not verify against requested series: '+' | '.join(titles[:6]))
        selected=(c.get('image') or {}).get('large') or (c.get('image') or {}).get('medium')
        if not selected: raise RuntimeError('no character image URL')
        rr=requests.get(selected,headers={'User-Agent':UA},timeout=45); rr.raise_for_status(); out=OUT/filename; colors=process(rr.content,out); size=out.stat().st_size; Image.open(out).verify(); status='OK' if size<=MAX_BYTES else 'PENDING_LOW_QUALITY'
        if status=='OK': ok.append(out)
        notes=f'Batched AniList lookup; search={search}; matched={c.get("name",{}).get("full")}; palette={colors}; media='+' | '.join(titles[:5])
        manifest.append({'filename':filename,'entity':entity,'series':series,'entity_type':'fictional_character','role':'primary','status':status,'source_page_url':c.get('siteUrl') or '','direct_asset_url':selected,'source_type':'AniList character database','license_note':'Authentic franchise character image located via AniList; reuse rights not asserted.','width':CANVAS,'height':CANVAS,'size_bytes':size,'size_kb':round(size/1024,2),'background_removed':'yes','canvas':'512x512','notes':notes})
        attrib.append({'filename':filename,'entity':entity,'source_page_url':c.get('siteUrl') or '','author_or_owner':'Underlying franchise rights holder','license':'Not specified by AniList','license_url':'','attribution_text':'Source URL retained for provenance.','rights_note':'Copyright/reuse rights not guaranteed.'})
    except Exception as e:
        notes=str(e); manifest.append({'filename':filename,'entity':entity,'series':series,'entity_type':'fictional_character','role':'primary','status':status,'source_page_url':c.get('siteUrl') if c else '','direct_asset_url':selected,'source_type':'AniList character database','license_note':'','width':'','height':'','size_bytes':'','size_kb':'','background_removed':'','canvas':'512x512','notes':notes})
    report.append({'filename':filename,'entity':entity,'query':f'"{entity}" "{series}" authentic character portrait; AniList search={search}','candidate_count':1 if c else 0,'selected_source':selected,'selection_reason':'Direct character lookup verified by franchise media list','rejected_notes':notes if status!='OK' else ''})

with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=manifest[0].keys()); w.writeheader(); w.writerows(manifest)
with (OUT/'SEARCH_REPORT.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=report[0].keys()); w.writeheader(); w.writerows(report)
with (OUT/'ASSET_ATTRIBUTION.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=attrib[0].keys() if attrib else ['filename']); w.writeheader(); w.writerows(attrib)
cols=5;thumb=150;labelh=30;gap=16;rows=max(1,math.ceil(len(ok)/cols));prev=Image.new('RGB',(gap+cols*(thumb+gap),gap+rows*(thumb+labelh+gap)),(245,245,245));d=ImageDraw.Draw(prev)
try: font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
except: font=ImageFont.load_default()
for j,p in enumerate(ok):
    rr=j//cols;cc=j%cols;x=gap+cc*(thumb+gap);y=gap+rr*(thumb+labelh+gap);tile=Image.new('RGBA',(thumb,thumb),(255,255,255,255));im=Image.open(p).convert('RGBA');im.thumbnail((thumb-8,thumb-8),Image.Resampling.LANCZOS);tile.alpha_composite(im,((thumb-im.width)//2,(thumb-im.height)//2));prev.paste(tile.convert('RGB'),(x,y));lab=p.stem[:20];bb=d.textbbox((0,0),lab,font=font);d.text((x+(thumb-(bb[2]-bb[0]))/2,y+thumb+5),lab,fill=(25,25,25),font=font)
prev.save(PREVIEW,quality=92)
with zipfile.ZipFile(ZIP,'w',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(OUT.iterdir()): z.write(p,arcname=p.name)
    z.write(PREVIEW,arcname='asset_pack_preview.jpg')
print(json.dumps({'requested':len(ASSETS),'ok':sum(x['status']=='OK' for x in manifest),'pending':sum(x['status']!='OK' for x in manifest),'zip':str(ZIP)}),flush=True)
