from __future__ import annotations
import csv, io, math, time, zipfile
from pathlib import Path
from urllib.parse import quote
import requests
from PIL import Image,ImageDraw,ImageFont,ImageOps

OUT=Path('cartoon_logo_pack_final_v4'); ZIP=Path('cartoon_logos_png_max130kb.zip'); PREVIEW=Path('cartoon_logos_preview.jpg')
MAX=130*1024; CANVAS=(512,256)
S=requests.Session(); S.headers.update({'User-Agent':'BarcharRace-cartoon-logo-pack/4.0 (BarChartStudio asset pack)','Accept':'image/avif,image/webp,image/png,image/*,*/*;q=0.8'})

def C(filename,width=1200): return f"https://commons.wikimedia.org/wiki/Special:Redirect/file/{quote(filename,safe='')}?width={width}"
def E(filename,width=1200): return f"https://en.wikipedia.org/wiki/Special:Redirect/file/{quote(filename,safe='')}?width={width}"
def CP(filename): return 'https://commons.wikimedia.org/wiki/File:'+quote(filename.replace(' ','_'),safe='()_,-–&!')
def EP(filename): return 'https://en.wikipedia.org/wiki/File:'+quote(filename.replace(' ','_'),safe='()_,-–&!')

# filename, title, candidate URLs, source page, source type, license note
I=[
('adventure_time.png','Adventure Time',[C('Adventure Time logo2.png')],CP('Adventure Time logo2.png'),'Wikimedia Commons','See source page; trademark may apply'),
('bugs_bunny.png','Bugs Bunny',['https://e7.pngegg.com/pngimages/965/903/png-clipart-the-bugs-bunny-birthday-blowout-mickey-mouse-lola-bunny-looney-tunes-s-of-cartoon-rabbits-white-mammal.png'], 'https://www.pngegg.com/es/png-nrejn','curated web','Reuse terms on source page'),
('ducktales.png','DuckTales',[C('DuckTales (1987 TV series) logo.svg')],CP('DuckTales (1987 TV series) logo.svg'),'Wikimedia Commons','See source page; trademark may apply'),
('gumball.png','The Amazing World of Gumball',[E('The Amazing World of Gumball logo.svg')],EP('The Amazing World of Gumball logo.svg'),'English Wikipedia media','See source page'),
('paw_patrol.png','PAW Patrol',[E('PAW Patrol Logo.png')],EP('PAW Patrol Logo.png'),'English Wikipedia media','See source page'),
('regular_show.png','Regular Show',['https://cn.i.cdn.ti-platform.com/cnemea/content/344/showpage/regular-show/uk/showlogo.png'], 'https://www.cartoonnetwork.co.uk/show/regular-show','official Cartoon Network','Official site asset; trademark/copyright may apply'),
('teen_titans_go.png','Teen Titans Go!',['https://image.pngaaa.com/941/109941-middle.png'], 'https://www.pngaaa.com/','curated web','Reuse terms on source page'),
('woody_woodpecker.png','Woody Woodpecker',[C('Woody Woodpecker logo.png')],CP('Woody Woodpecker logo.png'),'Wikimedia Commons','See source page; trademark may apply'),
('animaniacs.png','Animaniacs',[C('Animaniacs 1993 logo.svg')],CP('Animaniacs 1993 logo.svg'),'Wikimedia Commons','See source page; trademark may apply'),
('cocomelon.png','CoComelon',[C('Cocomelon-label-hd.png')],CP('Cocomelon-label-hd.png'),'Wikimedia Commons','See source page'),
('ed_edd_n_eddy.png','Ed, Edd n Eddy',[C('Ed, Edd n Eddy logo.png')],CP('Ed, Edd n Eddy logo.png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('looney_tunes.png','Looney Tunes',[C('Looney Tunes logo.svg')],CP('Looney Tunes logo.svg'),'Wikimedia Commons','See source page; trademark may apply'),
('peppa_pig.png','Peppa Pig',['https://www.citypng.com/public/uploads/preview/hd-peppa-pig-cartoon-logo-transparent-background-701751694771277yyzp8qnoq7.png'], 'https://www.citypng.com/','curated web','Reuse terms on source page'),
('rick_and_morty.png','Rick and Morty',['https://toppng.com/public/uploads/preview/rick-and-morty-logo-art-of-rick-and-morty-by-justin-roiland-11563648992tbukydvkeh.png'], 'https://toppng.com/','curated web','Reuse terms on source page'),
('the_flintstones.png','The Flintstones',[C('The Flintstones.png'),C('The Flintstones plain logo.svg')],CP('The Flintstones.png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('yogi_bear.png','Yogi Bear',[C('Yogi Bear logo.png')],CP('Yogi Bear logo.png'),'Wikimedia Commons','See source page; trademark may apply'),
('arthur.png','Arthur',[C('ArthurTVLogo.svg')],CP('ArthurTVLogo.svg'),'Wikimedia Commons','PD text-logo on source page'),
('courage.png','Courage the Cowardly Dog',['https://www.pngfind.com/pngs/m/10-100112_courage-the-cowardly-dog-courage-logo-mens-premium.png'], 'https://www.pngfind.com/','curated web','Reuse terms on source page'),
('family_guy.png','Family Guy',['https://image.pngaaa.com/553/691553-middle.png'], 'https://www.pngaaa.com/','curated web','Reuse terms on source page'),
('masha_and_bear.png','Masha and the Bear',[C('Masha and The Bear logo.png')],CP('Masha and The Bear logo.png'),'Wikimedia Commons','See source page'),
('phineas_and_ferb.png','Phineas and Ferb',['https://www.pngkit.com/png/detail/316-3165465_phineas-and-ferb-phineas-and-ferb-fonts.png'], 'https://www.pngkit.com/','curated web','Reuse terms on source page'),
('scooby_doo.png','Scooby-Doo',[C('Scooby doo logo.png')],CP('Scooby doo logo.png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('the_jetsons.png','The Jetsons',[C('The Jetsons (television series logo).png')],CP('The Jetsons (television series logo).png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('avatar_last_airbender.png','Avatar: The Last Airbender',[C('Avatar The Last Airbender logo.svg')],CP('Avatar The Last Airbender logo.svg'),'Wikimedia Commons','See source page; trademark may apply'),
('dexters_laboratory.png',"Dexter's Laboratory",[C('Dexter-logo.png')],CP('Dexter-logo.png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('felix_the_cat.png','Felix the Cat',['https://www.nicepng.com/png/detail/141-1415784_felix-the-cat-felix-the-cat-logo.png'], 'https://www.nicepng.com/ourpic/u2q8i1i1u2r5i1q8_felix-the-cat-felix-the-cat-logo/','curated web','Source lists personal/non-commercial use'),
('mickey_mouse.png','Mickey Mouse',['https://www.citypng.com/public/uploads/preview/disney-mickey-mouse-logo-image-png-701751694775006upcfdujvec.png?v=2026010223',C('Mickey Mouse & Friends logo.png')], 'https://commons.wikimedia.org/wiki/File:Mickey_Mouse_%26_Friends_logo.png','mixed/curated','See source page; trademark may apply'),
('pink_panther.png','The Pink Panther',[C('Pinkpanther-logo.svg')],CP('Pinkpanther-logo.svg'),'Wikimedia Commons','See source page; trademark may apply'),
('south_park.png','South Park',[C('South Park logo.png')],CP('South Park logo.png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('the_simpsons.png','The Simpsons',[C('The Simpsons Logo.png')],CP('The Simpsons Logo.png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('batman_tas.png','Batman: The Animated Series',[C('Batman- The Animated Series logo.png')],CP('Batman- The Animated Series logo.png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('dora_explorer.png','Dora the Explorer',[C('Dora the Explorer logo.png')],CP('Dora the Explorer logo.png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('futurama.png','Futurama',[C('Futurama 1999 logo.svg')],CP('Futurama 1999 logo.svg'),'Wikimedia Commons','See source page; trademark may apply'),
('miraculous_ladybug.png','Miraculous Ladybug',[C('Miraculous (franchise logo).png'),C('Miraculous, les aventures de Ladybug et Chat Noir Logo.png')],CP('Miraculous (franchise logo).png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('pokemon_tv.png','Pokémon',[C('International Pokémon logo.svg'),C('Pokemon logo.png')],CP('International Pokémon logo.svg'),'Wikimedia Commons','PD text-logo / see source page; trademark may apply'),
('spongebob.png','SpongeBob SquarePants',[C('SpongeBob SquarePants logo.png')],CP('SpongeBob SquarePants logo.png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('tmnt.png','Teenage Mutant Ninja Turtles',[C('Teenage Mutant Ninja Turtles 2022 franchise logo.png'),C('TMNT 2012 Logo.png')],CP('Teenage Mutant Ninja Turtles 2022 franchise logo.png'),'Wikimedia Commons','See source page; trademark may apply'),
('bluey.png','Bluey',[C('Bluey (TV series) logo.svg')],CP('Bluey (TV series) logo.svg'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('dragon_ball_z.png','Dragon Ball Z',[C('Dragon Ball Z Logo.png'),C('Dragon Ball Z logo.svg')],CP('Dragon Ball Z Logo.png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
('gravity_falls.png','Gravity Falls',[C('Gravity Falls logo (simplified).png')],CP('Gravity Falls logo (simplified).png'),'Wikimedia Commons','PD text-logo on source page'),
('mlp_friendship.png','My Little Pony: Friendship Is Magic',[E('My Little Pony Friendship Is Magic logo - 2017.svg')],EP('My Little Pony Friendship Is Magic logo - 2017.svg'),'English Wikipedia media','See source page; trademark may apply'),
('popeye.png','Popeye',['https://e7.pngegg.com/pngimages/532/524/png-clipart-popeye-logo-red-cartoons-popeye.png'], 'https://www.pngegg.com/es/png-vebrp','curated web','Source lists non-commercial/reuse terms; trademark may apply'),
('steven_universe.png','Steven Universe',['https://cdn.freebiesupply.com/logos/thumbs/2x/steven-universe-logo.png'], 'https://freebiesupply.com/logos/steven-universe-logo/','curated web','Reuse terms on source page; trademark may apply'),
('tom_and_jerry.png','Tom and Jerry',[C('Tom And Jerry Logo 2014.png'),C('Tom és Jerry.png')],CP('Tom And Jerry Logo 2014.png'),'Wikimedia Commons','PD text-logo on source page; trademark may apply'),
]

def get(url):
    last=None
    for a in range(6):
        try:
            r=S.get(url,timeout=50,allow_redirects=True)
            if r.status_code in (429,500,502,503,504): time.sleep(5+a*4); continue
            r.raise_for_status()
            if len(r.content)<150: raise RuntimeError('tiny payload')
            return r.content
        except Exception as e: last=e; time.sleep(2+a*2)
    raise RuntimeError(str(last))

def rmwhite(im):
    if im.getchannel('A').getextrema()!=(255,255) or im.width<2 or im.height<2:return im
    rgb=im.convert('RGB'); corners=[rgb.getpixel((0,0)),rgb.getpixel((rgb.width-1,0)),rgb.getpixel((0,rgb.height-1)),rgb.getpixel((rgb.width-1,rgb.height-1))]
    if not all(min(c)>245 for c in corners):return im
    px=im.load()
    for y in range(im.height):
        for x in range(im.width):
            r,g,b,a=px[x,y]; m=min(r,g,b)
            if m>=252:px[x,y]=(255,255,255,0)
            elif m>=244:px[x,y]=(r,g,b,int((252-m)/8*255))
    return im

def norm(data):
    with Image.open(io.BytesIO(data)) as src: im=ImageOps.exif_transpose(src).convert('RGBA')
    im=rmwhite(im); box=im.getchannel('A').getbbox(); im=im.crop(box) if box else im
    ratio=min(462/max(1,im.width),212/max(1,im.height)); ns=(max(1,int(im.width*ratio)),max(1,int(im.height*ratio))); im=im.resize(ns,Image.Resampling.LANCZOS)
    out=Image.new('RGBA',CANVAS,(255,255,255,0));out.alpha_composite(im,((512-ns[0])//2,(256-ns[1])//2));return out

def save(im,p):
    b=io.BytesIO();im.save(b,'PNG',optimize=True);d=b.getvalue()
    if len(d)<=MAX:p.write_bytes(d);return len(d)
    for colors in (256,192,128,96,64,48,32):
        q=im.quantize(colors=colors,method=Image.Quantize.FASTOCTREE);b=io.BytesIO();q.save(b,'PNG',optimize=True);d=b.getvalue()
        if len(d)<=MAX:p.write_bytes(d);return len(d)
    p.write_bytes(d);return len(d)

def preview(rows):
    cols=5;tw,th,lh,pad=220,130,28,14;nr=math.ceil(len(rows)/cols);o=Image.new('RGB',(pad+cols*(tw+pad),pad+nr*(th+lh+pad)),(245,245,245));dr=ImageDraw.Draw(o);font=ImageFont.load_default()
    for i,r in enumerate(rows):
        rr,cc=divmod(i,cols);x=pad+cc*(tw+pad);y=pad+rr*(th+lh+pad);tile=Image.new('RGBA',(tw,th),(255,255,255,255))
        with Image.open(OUT/r['filename']) as im:
            im=im.convert('RGBA');box=im.getchannel('A').getbbox() or (0,0,im.width,im.height);im=im.crop(box);ratio=min((tw-10)/im.width,(th-10)/im.height);ns=(max(1,int(im.width*ratio)),max(1,int(im.height*ratio)));im=im.resize(ns,Image.Resampling.LANCZOS);tile.alpha_composite(im,((tw-ns[0])//2,(th-ns[1])//2))
        o.paste(tile.convert('RGB'),(x,y));lab=r['filename'][:-4];bb=dr.textbbox((0,0),lab,font=font);dr.text((x+(tw-(bb[2]-bb[0]))/2,y+th+5),lab,fill=(20,20,20),font=font)
    o.save(PREVIEW,'JPEG',quality=92,optimize=True)

def main():
    OUT.mkdir(exist_ok=True)
    for p in OUT.iterdir():p.unlink()
    rows=[];fails=[]
    for idx,(fn,name,urls,page,stype,lic) in enumerate(I,1):
        print(f'[{idx}/{len(I)}] {name}',flush=True); data=None; used=''; errs=[]
        for u in urls:
            try:data=get(u);used=u;break
            except Exception as e:errs.append(f'{u}: {e}')
        if data is None:
            fails.append(f'{fn} | {name} | '+ ' || '.join(errs));print(' FAILED',errs[-1] if errs else 'no url',flush=True);continue
        try:
            im=norm(data);sz=save(im,OUT/fn)
            if sz>MAX:raise RuntimeError(f'{sz} > 130KB')
            rows.append({'filename':fn,'title':name,'width':Image.open(OUT/fn).width,'height':Image.open(OUT/fn).height,'size_bytes':sz,'size_kb':round(sz/1024,2),'status':'OK','source_url':page,'direct_media_url':used,'source_type':stype,'license_note':lic});print(' OK',round(sz/1024,1),'KB',flush=True)
        except Exception as e:fails.append(f'{fn} | {name} | process {e}');print(' PROCESS FAIL',e,flush=True)
        time.sleep(1.2)
    fields=['filename','title','width','height','size_bytes','size_kb','status','source_url','direct_media_url','source_type','license_note']
    with (OUT/'manifest.csv').open('w',newline='',encoding='utf-8-sig') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    if fails:(OUT/'FAILURES.txt').write_text('\n'.join(fails)+'\n',encoding='utf-8')
    if rows:preview(rows)
    if ZIP.exists():ZIP.unlink()
    with zipfile.ZipFile(ZIP,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.iterdir()):z.write(p,arcname=p.name)
        if PREVIEW.exists():z.write(PREVIEW,arcname='preview.jpg')
    print('FINAL',len(rows),'/',len(I),'fails',len(fails),flush=True)
    if len(rows)!=len(I):raise SystemExit(2)

if __name__=='__main__':main()
