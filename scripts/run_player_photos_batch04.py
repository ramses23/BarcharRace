from __future__ import annotations
import time
import requests
import build_player_photos_batch04 as b


def retry_download(url: str) -> bytes:
    last = None
    for i in range(8):
        try:
            r = b.S.get(url, timeout=120)
            if r.status_code == 429:
                wait = min(5 * (i + 1), 30)
                print(f'Rate limited by image host; waiting {wait}s before retry {i+1}/8', flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            time.sleep(1.0)
            return r.content
        except Exception as e:
            last = e
            time.sleep(min(3 * (i + 1), 20))
    raise RuntimeError(f'download failed after retries: {last}')


b.download = retry_download
raise SystemExit(b.main())
