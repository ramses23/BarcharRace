from pathlib import Path
import csv
import io
import zipfile
import requests
from PIL import Image, ImageOps

OUT = Path('kristen_hancher_pack')
OUT.mkdir(exist_ok=True)

SOURCE_PAGE = 'https://commons.wikimedia.org/wiki/File:Kristen_Hancher_2022.jpg'
DOWNLOAD_URL = 'https://commons.wikimedia.org/wiki/Special:Redirect/file/Kristen_Hancher_2022.jpg'
FILENAME = 'kristen_hancher.png'
MAX_BYTES = 130 * 1024

headers = {'User-Agent': 'BarChartStudioAssetBuilder/1.0 (public figure asset workflow)'}
r = requests.get(DOWNLOAD_URL, headers=headers, timeout=30, allow_redirects=True)
r.raise_for_status()
if not r.content or 'text/html' in (r.headers.get('content-type') or '').lower():
    raise RuntimeError('Expected image bytes but received non-image content')

src = Image.open(io.BytesIO(r.content)).convert('RGB')

# Source is already a close portrait. Use a centered square crop so the face stays large
# and readable at BarChartStudio logo scale.
side = min(src.width, src.height)
left = max(0, (src.width - side) // 2)
top = max(0, (src.height - side) // 2)
portrait = src.crop((left, top, left + side, top + side)).resize((512, 512), Image.Resampling.LANCZOS)

# Encode to PNG and quantize progressively until it meets the 130 KiB target.
out_path = OUT / FILENAME
for colors in (256, 192, 128, 96, 64, 48):
    q = portrait.quantize(colors=colors, method=Image.Quantize.MEDIANCUT)
    q.save(out_path, format='PNG', optimize=True)
    if out_path.stat().st_size <= MAX_BYTES:
        break
else:
    raise RuntimeError(f'Could not compress {FILENAME} below 130 KiB')

# Re-open to validate.
check = Image.open(out_path)
check.verify()
size_bytes = out_path.stat().st_size
if size_bytes > MAX_BYTES:
    raise RuntimeError('Output exceeds 130 KiB')

manifest_path = OUT / 'manifest.csv'
with manifest_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['filename','person_name','asset_type','width','height','size_bytes','size_kb','status','source_url','source_type','license_note','notes'])
    w.writerow([
        FILENAME,
        'Kristen Hancher',
        'primary_png',
        512,
        512,
        size_bytes,
        round(size_bytes / 1024, 2),
        'OK_NO_CUTOUT',
        SOURCE_PAGE,
        'wikimedia',
        'CC BY 3.0; source page attributes the underlying YouTube material and documents Commons review',
        'Face-focused square crop prepared for BarChartStudio; background retained to preserve portrait quality.'
    ])

readme = OUT / 'README.txt'
readme.write_text(
    'Kristen Hancher public-figure photo asset for BarChartStudio.\n'
    f'Source: {SOURCE_PAGE}\n'
    'License note: CC BY 3.0 per Wikimedia Commons file page.\n'
    'Output: 512x512 PNG, face-focused crop, <=130 KiB.\n',
    encoding='utf-8'
)

zip_path = Path('kristen_hancher_photo_pack_png_max130kb.zip')
with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    for p in (out_path, manifest_path, readme):
        z.write(p, arcname=p.name)

print(f'Created {zip_path} ({zip_path.stat().st_size} bytes)')
print(f'{FILENAME}: {size_bytes} bytes')
