from __future__ import annotations

import csv, io, math, time, zipfile
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

OUT=Path('cartoon_logo_pack_final')
ZIP=Path('cartoon_logos_png_max130kb.zip')
PREVIEW=Path('cartoon_logos_preview.jpg')
MAX_BYTES=130*1024
CANVAS=(512,256)
UA='BarcharRace-cartoon-logo-pack/3.0 (BarChartStudio identity asset pack)'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept':'*/*'})

# Curated mapping. Wikimedia/English-Wikipedia file titles are resolved through the
# MediaWiki image API so SVGs are rasterized server-side to PNG thumbnails.
ITEMS=[
 {'file':'adventure_time.png','name':'Adventure Time','wiki':'commons','title':'File:Adventure Time logo2.png'},
 {'file':'bugs_bunny.png','name':'Bugs Bunny','urls':['https://e7.pngegg.com/pngimages/965/903/png-clipart-the-bugs-bunny-birthday-blowout-mickey-mouse-lola-bunny-looney-tunes-s-of-cartoon-rabbits-white-mammal.png']},
 {'file':'ducktales.png','name':'DuckTales','wiki':'commons','title':'File:DuckTales (1987 TV series) logo.svg'},
 {'file':'gumball.png','name':'The Amazing World of Gumball','wiki':'enwiki','title':'File:The Amazing World of Gumball logo.svg'},
 {'file':'paw_patrol.png','name':'PAW Patrol','wiki':'enwiki','title':'File:PAW Patrol Logo.png'},
 {'file':'regular_show.png','name':'Regular Show','urls':['https://cn.i.cdn.ti-platform.com/cnemea/content/344/showpage/regular-show/uk/showlogo.png']},
 {'file':'teen_titans_go.png','name':'Teen Titans Go!','urls':['https://image.pngaaa.com/941/109941-middle.png']},
 {'file':'woody_woodpecker.png','name':'Woody Woodpecker','wiki':'commons','title':'File:Woody Woodpecker logo.png'},
 {'file':'animaniacs.png','name':'Animaniacs','wiki':'commons','title':'File:Animaniacs 1993 logo.svg'},
 {'file':'cocomelon.png','name':'CoComelon','wiki':'commons','title':'File:Cocomelon-label-hd.png'},
 {'file':'ed_edd_n_eddy.png','name':'Ed, Edd n Eddy','wiki':'commons','title':'File:Ed, Edd n Eddy logo.png'},
 {'file':'looney_tunes.png','name':'Looney Tunes','wiki':'commons','title':'File:Looney Tunes logo.svg'},
 {'file':'peppa_pig.png','name':'Peppa Pig','urls':['https://www.citypng.com/public/uploads/preview/hd-peppa-pig-cartoon-logo-transparent-background-701751694771277yyzp8qnoq7.png']},
 {'file':'rick_and_morty.png','name':'Rick and Morty','urls':['https://toppng.com/public/uploads/preview/rick-and-morty-logo-art-of-rick-and-morty-by-justin-roiland-11563648992tbukydvkeh.png']},
 {'file':'the_flintstones.png','name':'The Flintstones','urls':['https://en.vetores.org/wp-content/uploads/the-flintstones-logo-768x432.png']},
 {'file':'yogi_bear.png','name':'Yogi Bear','wiki':'commons','title':'File:Yogi Bear logo.png'},
 {'file':'arthur.png','name':'Arthur','urls':['https://pbskids.org/_next/image?q=75&url=https%3A%2F%2Fcms-assets.prod.pbskids.org%2Fglobal%2Fshow-logos%2FARUR-logo-v2.png&w=1200']},
 {'file':'courage.png','name':'Courage the Cowardly Dog','urls':['https://www.pngfind.com/pngs/m/10-100112_courage-the-cowardly-dog-courage-logo-mens-premium.png']},
 {'file':'family_guy.png','name':'Family Guy','urls':['https://image.pngaaa.com/553/691553-middle.png']},
 {'file':'masha_and_bear.png','name':'Masha and the Bear','wiki':'commons','title':'File:Masha and The Bear logo.png'},
 {'file':'phineas_and_ferb.png','name':'Phineas and Ferb','urls':['https://www.pngkit.com/png/detail/316-3165465_phineas-and-ferb-phineas-and-ferb-fonts.png']},
 {'file':'scooby_doo.png','name':'Scooby-Doo','wiki':'commons','title':'File:Scooby doo logo.png'},
 {'file':'the_jetsons.png','name':'The Jetsons','wiki':'commons','title':'File:The Jetsons (television series logo).png'},
 {'file':'avatar_last_airbender.png','name':'Avatar: The Last Airbender','wiki':'commons','title':'File:Avatar The Last Airbender logo.svg'},
 {'file':'dexters_laboratory.png','name':"Dexter's Laboratory",'wiki':'commons','title':'File:Dexter-logo.png'},
 {'file':'felix_the_cat.png','name':'Felix the Cat','urls':['https://www.nicepng.com/png/detail/141-1415784_felix-the-cat-felix-the-cat-logo.png']},
 {'file':'mickey_mouse.png','name':'Mickey Mouse','urls':['https://www.citypng.com/public/uploads/preview/disney-mickey-mouse-logo-image-png-701751694775006upcfdujvec.png?v=2026010223'],'wiki':'commons','title':'File:Mickey Mouse & Friends logo.png'},
 {'file':'pink_panther.png','name':'The Pink Panther','wiki':'commons','title':'File:Pinkpanther-logo.svg'},
 {'file':'south_park.png','name':'South Park','wiki':'commons','title':'File:South Park logo.png'},
 {'file':'the_simpsons.png','name':'The Simpsons','wiki':'commons','title':'File:The Simpsons Logo.png'},
 {'file':'batman_tas.png','name':'Batman: The Animated Series','wiki':'commons','title':'File:Batman- The Animated Series logo.png'},
 {'file':'dora_explorer.png','name':'Dora the Explorer','wiki':'commons','title':'File:Dora the Explorer logo.png'},
 {'file':'futurama.png','name':'Futurama','wiki':'commons','title':'File:Futurama 1999 logo.svg'},
 {'file':'miraculous_ladybug.png','name':'Miraculous Ladybug','wiki':'commons','title':'File:Miraculous (franchise logo).png'},
 {'file':'pokemon_tv.png','name':'Pokémon','wiki':'commons','title':'File:International Pokémon logo.svg'},
 {'file':'spongebob.png','name':'SpongeBob SquarePants','wiki':'commons','title':'File:SpongeBob SquarePants logo.png'},
 {'file':'tmnt.png','name':'Teenage Mutant Ninja Turtles','wiki':'commons','title':'File:Teenage Mutant Ninja Turtles 2022 franchise logo.png'},
 {'file':'bluey.png','name':'Bluey','wiki':'commons','title':'File:Bluey (TV series) logo.svg'},
 {'file':'dragon_ball_z.png','name':'Dragon Ball Z','wiki':'commons','title':'File:Dragon Ball Z Logo.png'},
 {'file':'gravity_falls.png','name':'Gravity Falls','wiki':'commons','title':'File:Gravity Falls logo (simplified).png'},
 {'file':'mlp_friendship.png','name':'My Little Pony: Friendship Is Magic','wiki':'enwiki','title':'File:My Little Pony Friendship Is Magic logo - 2017.svg'},
 {'file':'popeye.png','name':'Popeye','urls':['https://e7.pngegg.com/pngimages/532/524/png-clipart-popeye-logo-red-cartoons-popeye.png']},
 {'file':'steven_universe.png','name':'Steven Universe','urls':['https://cdn.freebiesupply.com/logos/thumbs/2x/steven-universe-logo.png']},
 {'file':'tom_and_jerry.png','name':'Tom and Jerry','wiki':'commons','title':'File:Tom And Jerry Logo 2014.png'},
]

API={'commons':'https://commons.wikimedia.org/w/api.php','enwiki':'https://en.wikipedia.org/w/api.php'}

def get(url, attempts=5):
    last=None
    for a in range(attempts):
        try:
            r=S.get(url,timeout=45,allow_redirects=True)
            if r.status_code in (429,502,503,504):
                time.sleep(4+a*3); continue
            r.raise_for_status()
            if len(r.content)<150: raise RuntimeError('tiny payload')
            return r
        except Exception as e:
            last=e; time.sleep(2+a*2)
    raise RuntimeError(f'download failed: {last}')

def wiki_media(item):
    api=API[item['wiki']]
    params={'action':'query','format':'json','titles':item['title'],'prop':'imageinfo','iiprop':'url|size|mime|extmetadata','iiurlwidth':1200}
    r=S.get(api,params=params,timeout=40); r.raise_for_status(); data=r.json()
    pages=(data.get('query',{}).get('pages',{}) or {}).values()
    p=next(iter(pages),{})
    if 'missing' in p: raise RuntimeError('wiki file missing')
    ii=(p.get('imageinfo') or [{}])[0]
    url=ii.get('thumburl') or ii.get('url')
    if not url: raise RuntimeError('wiki media URL absent')
    ext=ii.get('extmetadata') or {}
    return {
      'url':url,'page':ii.get('descriptionurl') or f"https://{ 'commons.wikimedia.org' if item['wiki']=='commons' else 'en.wikipedia.org'}/wiki/{quote(item['title'].replace(' ','_'))}",
      'source':item['wiki'],'source_file':p.get('title',item['title']),
      'license':(ext.get('LicenseShortName') or {}).get('value',''),
      'artist':restrip((ext.get('Artist') or {}).get('value','')),
    }

def restrip(s):
    import re
    return re.sub('<[^>]+>',' ',s or '').replace('&nbsp;',' ').strip()

def resolve(item):
    candidates=[]
    # Preferred explicit direct URLs first for hand-curated external assets.
    for u in item.get('urls',[]): candidates.append({'url':u,'page':u,'source':'curated_web','source_file':'','license':'License/reuse terms on source site; see URL','artist':''})
    if item.get('wiki'):
        try: candidates.append(wiki_media(item))
        except Exception as e: print('   wiki metadata fallback failed:',e,flush=True)
    if not candidates: raise RuntimeError('no source candidate')
    errors=[]
    for c in candidates:
        try:
            r=get(c['url']); return r.content,c
        except Exception as e: errors.append(str(e))
    raise RuntimeError(' | '.join(errors))

def remove_white_bg(im):
    # Conservative: only if corners indicate a uniformly white backdrop.
    if im.getchannel('A').getextrema()!=(255,255) or im.width<2 or im.height<2: return im
    rgb=im.convert('RGB'); cs=[rgb.getpixel((0,0)),rgb.getpixel((rgb.width-1,0)),rgb.getpixel((0,rgb.height-1)),rgb.getpixel((rgb.width-1,rgb.height-1))]
    if not all(min(c)>245 for c in cs): return im
    px=im.load()
    for y in range(im.height):
        for x in range(im.width):
            r,g,b,a=px[x,y]
            # Smooth-ish alpha transition for near-white antialiasing.
            m=min(r,g,b)
            if m>=252: px[x,y]=(255,255,255,0)
            elif m>=242:
                alpha=max(0,min(255,int((252-m)/10*255)))
                px[x,y]=(r,g,b,alpha)
    return im

def normalize(data):
    with Image.open(io.BytesIO(data)) as src:
        im=ImageOps.exif_transpose(src).convert('RGBA')
    im=remove_white_bg(im)
    box=im.getchannel('A').getbbox()
    if box: im=im.crop(box)
    ratio=min(462/max(1,im.width),212/max(1,im.height))
    ns=(max(1,int(im.width*ratio)),max(1,int(im.height*ratio)))
    im=im.resize(ns,Image.Resampling.LANCZOS)
    out=Image.new('RGBA',CANVAS,(255,255,255,0)); out.alpha_composite(im,((512-ns[0])//2,(256-ns[1])//2)); return out

def save_limit(im,path):
    b=io.BytesIO(); im.save(b,'PNG',optimize=True); data=b.getvalue()
    if len(data)<=MAX_BYTES: path.write_bytes(data); return len(data)
    for colors in (256,192,128,96,64,48,32):
        q=im.quantize(colors=colors,method=Image.Quantize.FASTOCTREE)
        b=io.BytesIO(); q.save(b,'PNG',optimize=True); data=b.getvalue()
        if len(data)<=MAX_BYTES: path.write_bytes(data); return len(data)
    for factor in (.9,.8,.7):
        sm=im.resize((int(512*factor),int(256*factor)),Image.Resampling.LANCZOS)
        b=io.BytesIO(); sm.save(b,'PNG',optimize=True); data=b.getvalue()
        if len(data)<=MAX_BYTES: path.write_bytes(data); return len(data)
    path.write_bytes(data); return len(data)

def make_preview(rows):
    cols=5; tw,th,lh,pad=220,130,30,14; nr=math.ceil(len(rows)/cols)
    out=Image.new('RGB',(pad+cols*(tw+pad),pad+nr*(th+lh+pad)),(245,245,245)); d=ImageDraw.Draw(out); font=ImageFont.load_default()
    for i,r in enumerate(rows):
        rr,cc=divmod(i,cols); x=pad+cc*(tw+pad); y=pad+rr*(th+lh+pad); tile=Image.new('RGBA',(tw,th),(255,255,255,255))
        with Image.open(OUT/r['filename']) as im:
            im=im.convert('RGBA'); box=im.getchannel('A').getbbox() or (0,0,im.width,im.height); im=im.crop(box)
            ratio=min((tw-12)/max(1,im.width),(th-12)/max(1,im.height)); ns=(max(1,int(im.width*ratio)),max(1,int(im.height*ratio))); im=im.resize(ns,Image.Resampling.LANCZOS); tile.alpha_composite(im,((tw-ns[0])//2,(th-ns[1])//2))
        out.paste(tile.convert('RGB'),(x,y)); lab=r['filename'][:-4]; bb=d.textbbox((0,0),lab,font=font); d.text((x+(tw-(bb[2]-bb[0]))/2,y+th+6),lab,fill=(20,20,20),font=font)
    out.save(PREVIEW,'JPEG',quality=92,optimize=True)

def main():
    OUT.mkdir(exist_ok=True)
    for p in OUT.iterdir(): p.unlink()
    rows=[]; failures=[]
    for i,item in enumerate(ITEMS,1):
        print(f'[{i}/{len(ITEMS)}] {item["name"]}',flush=True)
        try:
            data,c=resolve(item); im=normalize(data); size=save_limit(im,OUT/item['file'])
            if size>MAX_BYTES: raise RuntimeError(f'file still exceeds 130 KB: {size}')
            rows.append({'filename':item['file'],'title':item['name'],'width':Image.open(OUT/item['file']).width,'height':Image.open(OUT/item['file']).height,'size_bytes':size,'size_kb':round(size/1024,2),'status':'OK','source_file':c['source_file'],'source_url':c['page'],'source_type':c['source'],'license':c['license'],'artist':c['artist']})
            print('   OK',round(size/1024,1),'KB',c['source_file'] or c['source'],flush=True)
        except Exception as e:
            failures.append(f"{item['file']} | {item['name']} | {e}"); print('   FAILED',e,flush=True)
        time.sleep(.9)
    if failures:
        (OUT/'FAILURES.txt').write_text('\n'.join(failures)+'\n',encoding='utf-8')
    fields=['filename','title','width','height','size_bytes','size_kb','status','source_file','source_url','source_type','license','artist']
    with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    if rows: make_preview(rows)
    if ZIP.exists(): ZIP.unlink()
    with zipfile.ZipFile(ZIP,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.iterdir()): z.write(p,arcname=p.name)
        if PREVIEW.exists(): z.write(PREVIEW,arcname='preview.jpg')
    print(f'FINAL {len(rows)}/{len(ITEMS)}',flush=True)
    if len(rows)!=len(ITEMS): raise SystemExit(2)
    if any((OUT/i['file']).stat().st_size>MAX_BYTES for i in ITEMS): raise SystemExit('size validation failed')

if __name__=='__main__': main()
