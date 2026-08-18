from __future__ import annotations

import csv
import time
import zipfile
from pathlib import Path
import requests

import build_player_photos_batch04 as core

core.ROOT = Path("photo_pack_batch06")
core.ZIP_PATH = Path("football_player_photos_batch06_png_max130kb.zip")
core.USER_AGENT = "BarcharRace-photo-pack/2.4 (BarChartStudio final missing-player pack)"
core.S.headers.update({"User-Agent": core.USER_AGENT})

# These 13 were already verified to resolve correctly in the previous run.
core.PLAYERS = [
    {"player":"Davor Šuker","file":"davor_uker.png","titles":["Davor Šuker","Davor Suker"]},
    {"player":"Edin Džeko","file":"edin_d_eko.png","titles":["Edin Džeko","Edin Dzeko"]},
    {"player":"Gabino Sosa","file":"gabino_sosa.png","titles":["Gabino Sosa"]},
    {"player":"Gheorghe Hagi","file":"gheorghe_hagi.png","titles":["Gheorghe Hagi"]},
    {"player":"Héctor Scarone","file":"h_ctor_scarone.png","titles":["Héctor Scarone","Hector Scarone"]},
    {"player":"Isidro Lángara","file":"isidro_l_ngara.png","titles":["Isidro Lángara","Isidro Langara"]},
    {"player":"Joachim Streich","file":"joachim_streich.png","titles":["Joachim Streich"]},
    {"player":"José Pérez","file":"jos_p_rez.png","titles":["José Pérez (Uruguayan footballer)","José Pérez footballer Uruguay","Jose Perez footballer Uruguay"]},
    {"player":"Mahmoud Mokhtar El-Tetsh","file":"mahmoud_mokhtar_el_tetsh.png","titles":["Mokhtar El-Tetsh","Mahmoud Mokhtar El-Tetsh"]},
    {"player":"Max Abegglen","file":"max_abegglen.png","titles":["Max Abegglen"]},
    {"player":"Pelé","file":"pel.png","titles":["Pelé","Pele"]},
    {"player":"Robert Lewandowski","file":"robert_lewandowski.png","titles":["Robert Lewandowski"]},
    {"player":"Ronaldo Nazário","file":"ronaldo.png","titles":["Ronaldo (Brazilian footballer)","Ronaldo Nazário","Ronaldo Nazario"]},
]


def download_with_retry(url: str):
    last = None
    for attempt in range(4):
        try:
            time.sleep(0.9)
            r = core.S.get(url, timeout=120)
            if r.status_code == 429:
                raise requests.HTTPError("429 Too Many Requests")
            r.raise_for_status()
            return r.content
        except Exception as exc:
            last = exc
            time.sleep(min(2 ** attempt, 10))
    raise RuntimeError(f"download failed after retries: {last}")

core.download = download_with_retry


def append_unresolved_na() -> None:
    manifest = core.ROOT / "manifest.csv"
    fields = [
        "filename","person_name","width","height","size_bytes","size_kb","status",
        "face_detected","source_file","source_url","license","artist","wikidata_id","resolution_method"
    ]
    with manifest.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    rows.append({
        "filename":"na.png","person_name":"na","width":"","height":"","size_bytes":"","size_kb":"",
        "status":"AMBIGUOUS_INPUT","face_detected":"","source_file":"","source_url":"","license":"",
        "artist":"","wikidata_id":"","resolution_method":"Filename 'na' does not uniquely identify a footballer; no image created to avoid assigning the wrong person."
    })
    with manifest.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
    (core.ROOT / "UNRESOLVED_na.txt").write_text(
        "The source filename 'na' is ambiguous and does not uniquely identify a footballer. No image was fabricated or guessed.\n",
        encoding="utf-8"
    )
    if core.ZIP_PATH.exists():
        core.ZIP_PATH.unlink()
    with zipfile.ZipFile(core.ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(core.ROOT.iterdir()):
            z.write(p, arcname=p.name)


if __name__ == "__main__":
    core.main()
    append_unresolved_na()
    pngs = list(core.ROOT.glob("*.png"))
    if len(pngs) != 13:
        raise SystemExit(f"Expected 13 PNGs, found {len(pngs)}")
    if any(p.stat().st_size > core.MAX_BYTES for p in pngs):
        raise SystemExit("At least one PNG exceeds 130 KB")
    print("Batch 06A: 13 verified PNGs; na flagged ambiguous.")
