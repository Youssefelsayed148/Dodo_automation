"""Download the fonts bundled into PDFs into backend/app/pdf/fonts/.

Fonts are SIL Open Font License (google/fonts repository). Without them the
PDFs fall back to DejaVu Sans, which also shapes Arabic correctly, but the
book looks nicer with Fredoka/Nunito and Noto Naskh Arabic.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / "backend" / "app" / "pdf" / "fonts"
BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl"
FONTS = {
    "Fredoka-Variable.ttf": f"{BASE}/fredoka/Fredoka%5Bwdth,wght%5D.ttf",
    "Nunito-Variable.ttf": f"{BASE}/nunito/Nunito%5Bwght%5D.ttf",
    "NotoNaskhArabic-Variable.ttf": f"{BASE}/notonaskharabic/NotoNaskhArabic%5Bwght%5D.ttf",
    "Cairo-Variable.ttf": f"{BASE}/cairo/Cairo%5Bslnt,wght%5D.ttf",
}


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    ok = True
    for name, url in FONTS.items():
        target = DEST / name
        if target.exists() and target.stat().st_size > 10_000:
            print(f"ok      {name}")
            continue
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                data = r.read()
            if len(data) < 10_000:
                raise ValueError("file too small")
            target.write_bytes(data)
            print(f"fetched {name} ({len(data) // 1024} KB)")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"FAILED  {name}: {e}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
