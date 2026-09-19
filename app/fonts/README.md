# Bundled UI fonts

Drop the `.ttf` files here. The app registers them for its own process with
`AddFontResourceEx(..., FR_PRIVATE)`, so nothing is installed system-wide, and
falls back to Segoe UI and Consolas when this directory is empty.

| Family | Used for | Licence | Source |
| --- | --- | --- | --- |
| Be Vietnam Pro | All UI text | OFL 1.1 | https://fonts.google.com/specimen/Be+Vietnam+Pro |
| JetBrains Mono | File list rows | OFL 1.1 | https://fonts.google.com/specimen/JetBrains+Mono |

Regular and Bold weights are enough. Be Vietnam Pro is drawn for Vietnamese
diacritics, which stack tall and collide in fonts that were not designed for them.

Both are OFL, so redistributing them inside the packaged app is fine. Keep the
`OFL.txt` that ships with each family next to the fonts.
