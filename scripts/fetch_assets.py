#!/usr/bin/env python3
"""Copy the layout model and font into app/assets so a packaged build runs offline.

Both files come from babeldoc's own downloader, so this asks the library where
they landed rather than guessing at its cache layout. Needs network once.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

ASSETS = SKILL_ROOT / "app" / "assets"
MODEL_NAME = "doclayout.onnx"
FONT_NAME = "GoNotoKurrent-Regular.ttf"


def main() -> int:
    try:
        from babeldoc.assets.assets import (
            get_doclayout_onnx_model_path,
            get_font_and_metadata,
        )
    except ImportError:
        print(
            "error: dependencies are missing. Run:\n"
            f'  "{sys.executable}" -m pip install -r "{SKILL_ROOT / "requirements.txt"}"',
            file=sys.stderr,
        )
        return 2

    ASSETS.mkdir(parents=True, exist_ok=True)

    for label, source, name in (
        ("model", Path(get_doclayout_onnx_model_path()), MODEL_NAME),
        ("font", Path(get_font_and_metadata(FONT_NAME)[0]), FONT_NAME),
    ):
        destination = ASSETS / name
        shutil.copyfile(source, destination)
        print(f"{label:<6} {destination}  ({source.stat().st_size / 1e6:.1f} MB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
