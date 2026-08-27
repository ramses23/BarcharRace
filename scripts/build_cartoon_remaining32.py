from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_cartoon_logo_pack_final_v4 as m

WANTED = {
    'regular_show.png','teen_titans_go.png','ed_edd_n_eddy.png','looney_tunes.png',
    'peppa_pig.png','rick_and_morty.png','the_flintstones.png','yogi_bear.png',
    'arthur.png','courage.png','family_guy.png','masha_and_bear.png',
    'phineas_and_ferb.png','scooby_doo.png','the_jetsons.png','avatar_last_airbender.png',
    'dexters_laboratory.png','felix_the_cat.png','mickey_mouse.png','pink_panther.png',
    'south_park.png','the_simpsons.png','batman_tas.png','dora_explorer.png',
    'futurama.png','miraculous_ladybug.png','pokemon_tv.png','spongebob.png',
    'tmnt.png','bluey.png','dragon_ball_z.png','tom_and_jerry.png'
}

items=[]
for item in m.I:
    fn=item[0]
    if fn not in WANTED:
        continue
    if fn == 'batman_tas.png':
        item = (item[0], item[1], [m.C('Batman- The Animated Series logo.svg')], m.CP('Batman- The Animated Series logo.svg'), 'Wikimedia Commons', 'PD text-logo on source page; trademark may apply')
    items.append(item)

m.I=items
m.OUT=Path('cartoon_remaining32')
m.ZIP=Path('cartoon_remaining32_png_max130kb.zip')
m.PREVIEW=Path('cartoon_remaining32_preview.jpg')
m.main()
