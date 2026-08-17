from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

import requests
from PIL import Image, ImageOps

ROOT = Path('photo_pack_batch02')
ZIP_PATH = Path('football_player_photos_batch02_png_max130kb.zip')
MAX_BYTES = 130 * 1024
FILE = 'dem_stenes_correia_de_syllos.png'
PAGE_URL = 'https://commons.wikimedia.org/wiki/File:A.A._das_Palmeiras_-_1915.jpg'
IMAGE_URL = 'https://commons.wikimedia.org/wiki/Special:Redirect/file/A.A._das_Palmeiras_-_1915.jpg?width=1200'


def save_small_png(image: Image.Image, destination: Path) -> tuple[int, int, int]:
    best = None
    for side in (512, 448, 384, 320):
        img = ImageOps.pad(image.convert('RGB'), (side, side), method=Image.Resampling.LANCZOS, color='white', centering=(0.5, 0.5))
        for colors in (192, 128, 96, 64):
            q = img.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
            b = io.BytesIO(); q.save(b, 'PNG', optimize=True); data = b.getvalue()
            if best is None or len(data) < len(best[0]):
                best = (data, side)
            if len(data) <= MAX_BYTES:
                destination.write_bytes(data)
                return side, side, len(data)
    destination.write_bytes(best[0])
    return best[1], best[1], len(best[0])


def main() -> int:
    ROOT.mkdir(exist_ok=True)
    response = requests.get(IMAGE_URL, timeout=120, headers={'User-Agent':'BarcharRace-photo-pack/2.1'})
    response.raise_for_status()
    with Image.open(io.BytesIO(response.content)) as image:
        width, height, size_bytes = save_small_png(image, ROOT / FILE)

    manifest = ROOT / 'manifest.csv'
    rows = []
    if manifest.exists():
        with manifest.open('r', encoding='utf-8-sig', newline='') as h:
            rows = list(csv.DictReader(h))
    rows = [r for r in rows if r.get('filename') != FILE]
    fields = ['filename','person_name','width','height','size_bytes','size_kb','status','face_detected','source_file','source_url','license','artist','wikidata_id','resolution_method']
    rows.append({
        'filename': FILE,
        'person_name': 'Demósthenes Correia de Syllos',
        'width': width,
        'height': height,
        'size_bytes': size_bytes,
        'size_kb': round(size_bytes/1024, 2),
        'status': 'OK_TEAM_PHOTO_FALLBACK',
        'face_detected': 'no',
        'source_file': 'A.A. das Palmeiras - 1915.jpg',
        'source_url': PAGE_URL,
        'license': 'Public domain',
        'artist': 'Unknown author',
        'wikidata_id': '',
        'resolution_method': 'Curated historical team-photo fallback; Demósthenes was a member of the 1915 championship side',
    })
    with manifest.open('w', encoding='utf-8-sig', newline='') as h:
        w = csv.DictWriter(h, fieldnames=fields); w.writeheader(); w.writerows(rows)

    if ZIP_PATH.exists(): ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(ROOT.iterdir()):
            z.write(path, arcname=path.name)

    pngs = list(ROOT.glob('*.png'))
    if len(pngs) != 20:
        raise RuntimeError(f'Expected 20 PNGs, found {len(pngs)}')
    oversized = [p.name for p in pngs if p.stat().st_size > MAX_BYTES]
    if oversized:
        raise RuntimeError('Oversized PNGs: ' + ', '.join(oversized))
    print('Batch 02 patched and validated: 20 PNGs, all <=130 KB')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
