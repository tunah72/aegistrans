# Bundled runtime assets

`scripts/fetch_assets.py` fills this directory so a packaged build translates
without network access on its first run:

| File | Purpose |
| --- | --- |
| `doclayout.onnx` | Page layout detection model |
| `GoNotoKurrent-Regular.ttf` | Output PDF font, covers Latin and Vietnamese |

Both are downloaded through babeldoc's own asset loader. When the directory is
empty the app falls back to downloading them on first use.
