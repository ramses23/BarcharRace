from __future__ import annotations

from PIL import ImageOps
import build_player_photos_batch06_direct as pack

# Replace the two sources that were blocked/unavailable in the first direct-source run.
for p in pack.PLAYERS:
    if p['person'] == 'Hernando Salazar':
        p.pop('page', None)
        p['url'] = 'https://www.memoriachilena.gob.cl/602/articles-98923_thumbnail.jpg'
        p['source'] = 'Memoria Chilena / Biblioteca Nacional de Chile — Chile national team, 1916'
        p['license'] = 'Patrimonio cultural común; Memoria Chilena states this document may be used and reproduced freely'
        p['selector'] = 'full_historical_team'
    elif p['person'] == 'Ronaldo Nazário':
        p['url'] = 'https://upload.wikimedia.org/wikipedia/commons/d/d5/Ronaldo_2002_cropped.jpg'
        p['source'] = 'Wikimedia Commons — Ronaldo 2002 cropped.jpg'
        p['license'] = 'CC BY-SA 4.0'

_original_crop_face = pack.crop_face

def crop_face_with_historical_fallback(im, selector=None):
    if selector == 'full_historical_team':
        im = ImageOps.exif_transpose(im).convert('RGB')
        # Keep the complete historical team photo instead of guessing which face is Salazar.
        return ImageOps.fit(im, (pack.TARGET, pack.TARGET), method=pack.Image.Resampling.LANCZOS, centering=(0.5, 0.5)), False
    return _original_crop_face(im, selector)

pack.crop_face = crop_face_with_historical_fallback

if __name__ == '__main__':
    pack.main()
