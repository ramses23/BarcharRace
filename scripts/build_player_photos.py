from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

USER_AGENT = "BarcharRace-photo-builder/1.0 (GitHub Actions; ramses23/BarcharRace)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
ENWIKI_API = "https://en.wikipedia.org/w/api.php"

PLAYERS = [
    ("Cristiano Ronaldo", "Cristiano Ronaldo", "cristiano_ronaldo.png"),
    ("Lionel Messi", "Lionel Messi", "lionel_messi.png"),
    ("Pelé", "Pelé", "pele.png"),
    ("Romário", "Romário", "romario.png"),
    ("Ferenc Puskás", "Ferenc Puskás", "ferenc_puskas.png"),
    ("Josef Bican", "Josef Bican", "josef_bican.png"),
    ("Robert Lewandowski", "Robert Lewandowski", "robert_lewandowski.png"),
    ("Jimmy Jones", "Jimmy Jones (footballer, born 1928)", "jimmy_jones.png"),
    ("Gerd Müller", "Gerd Müller", "gerd_muller.png"),
    ("Joe Bambrick", "Joe Bambrick", "joe_bambrick.png"),
    ("Abe Lenstra", "Abe Lenstra", "abe_lenstra.png"),
    ("Luis Suárez", "Luis Suárez", "luis_suarez.png"),
    ("Túlio Maravilha", "Túlio Maravilha", "tulio_maravilha.png"),
    ("Eusébio", "Eusébio", "eusebio.png"),
    ("Zlatan Ibrahimović", "Zlatan Ibrahimović", "zlatan_ibrahimovic.png"),
]

# Explicitly selected Commons portraits where the Wikidata P18 image is absent,
# unsuitable, or less reliable. Never map a failed player to another person.
COMMONS_OVERRIDES = {
    "Ferenc Puskás": "Ferenc Puskás (cropped).jpg",
    "Josef Bican": "Josef Bican 1940.jpg",
    "Luis Suárez": "U09 Luis Suárez 3470.jpg",
}


def request_json(url: str, params: dict[str, Any], attempts: int = 5) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.load(response)
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def download(url: str, destination: Path, attempts: int = 5) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                destination.write_bytes(response.read())
            return
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt)


def strip_markup(value: str | None) -> str:
    if not value:
        return "Unknown"
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "Unknown"


def wikidata_id_for_page(page_title: str) -> str:
    data = request_json(
        ENWIKI_API,
        {
            "action": "query",
            "format": "json",
            "redirects": 1,
            "prop": "pageprops",
            "titles": page_title,
        },
    )
    page = next(iter(data["query"]["pages"].values()))
    qid = page.get("pageprops", {}).get("wikibase_item")
    if not qid:
        raise RuntimeError(f"No Wikidata item for English Wikipedia page: {page_title}")
    return qid


def commons_title_from_wikidata(qid: str) -> str:
    data = request_json(
        WIKIDATA_API,
        {
            "action": "wbgetentities",
            "format": "json",
            "ids": qid,
            "props": "claims",
        },
    )
    claims = data["entities"][qid].get("claims", {})
    p18 = claims.get("P18", [])
    if not p18:
        raise RuntimeError(f"{qid} has no Wikidata P18 photograph")
    return p18[0]["mainsnak"]["datavalue"]["value"]


def commons_info(file_title: str) -> dict[str, Any]:
    data = request_json(
        COMMONS_API,
        {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata",
            "iiurlwidth": 1200,
            "titles": f"File:{file_title}",
        },
    )
    page = next(iter(data["query"]["pages"].values()))
    if "missing" in page:
        raise RuntimeError(f"Commons file does not exist: {file_title}")
    info = page["imageinfo"][0]
    mime = info.get("mime", "")
    if not mime.startswith("image/"):
        raise RuntimeError(f"Commons resource is not an image: {file_title} ({mime})")
    return info


def convert_square(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        image.load()
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.fit(image, (512, 512), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        image.save(destination, "PNG", optimize=True)
    with Image.open(destination) as check:
        check.verify()
    with Image.open(destination) as check:
        if check.format != "PNG" or check.size != (512, 512):
            raise RuntimeError(f"Invalid converted image: {destination}")


def main() -> int:
    root = Path("photos")
    raw = Path(".photo-downloads")
    root.mkdir(exist_ok=True)
    raw.mkdir(exist_ok=True)

    manifest: list[dict[str, Any]] = []
    attributions = [
        "# Player photo attributions",
        "",
        "All images are real photographs. Files were retrieved from Wikimedia Commons thumbnails and transformed only by centered square cropping and resizing to 512 × 512 pixels.",
        "",
        "| Player | Source | Commons file URL | Author | License |",
        "|---|---|---|---|---|",
    ]
    failures: list[str] = []

    for player, page_title, output_name in PLAYERS:
        record: dict[str, Any] = {
            "player": player,
            "file": output_name,
            "status": "failed",
            "dimensions": None,
            "sha256": None,
        }
        try:
            qid = wikidata_id_for_page(page_title)
            commons_title = COMMONS_OVERRIDES.get(player) or commons_title_from_wikidata(qid)
            info = commons_info(commons_title)
            metadata = info.get("extmetadata", {})
            thumb_url = info.get("thumburl") or info["url"]
            source_url = info.get("descriptionurl") or (
                "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(commons_title.replace(" ", "_"))
            )
            author = strip_markup(metadata.get("Artist", {}).get("value"))
            license_name = strip_markup(
                metadata.get("LicenseShortName", {}).get("value")
                or metadata.get("UsageTerms", {}).get("value")
            )
            raw_path = raw / (output_name + ".download")
            download(thumb_url, raw_path)
            destination = root / output_name
            convert_square(raw_path, destination)
            digest = hashlib.sha256(destination.read_bytes()).hexdigest()
            record.update(
                {
                    "status": "ok",
                    "dimensions": [512, 512],
                    "sha256": digest,
                    "wikidata_id": qid,
                    "commons_file": commons_title,
                    "source_url": source_url,
                    "author": author,
                    "license": license_name,
                }
            )
            attributions.append(
                f"| {player} | Wikimedia Commons | {source_url} | {author.replace('|', '/')} | {license_name.replace('|', '/')} |"
            )
            print(f"OK: {player} -> {output_name}")
        except Exception as exc:
            message = f"{player}: {type(exc).__name__}: {exc}"
            failures.append(message)
            record["error"] = message
            attributions.append(f"| {player} | FAILED | — | — | — |")
            print(f"FAILED: {message}", file=sys.stderr)
        manifest.append(record)

    (root / "ATTRIBUTIONS.md").write_text("\n".join(attributions) + "\n", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "expected_images": len(PLAYERS),
                "successful_images": sum(item["status"] == "ok" for item in manifest),
                "failed_images": sum(item["status"] != "ok" for item in manifest),
                "items": manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "DOWNLOAD_FAILURES.log").write_text(
        "\n".join(failures) + ("\n" if failures else "No download failures.\n"), encoding="utf-8"
    )

    with zipfile.ZipFile("photos.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.iterdir()):
            archive.write(path, arcname=f"photos/{path.name}")

    if failures:
        print(f"Artifact created with {len(failures)} failure(s).", file=sys.stderr)
        return 1
    print("Artifact created successfully with all 15 photographs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
