# PDF preservation contract

The bundled core translates ordinary text while retaining document structures whose meaning depends on exact placement. These rules are product behavior and require regression coverage when changed.

## Formula and code protection

- Formula glyphs remain original PDF operators and are represented by placeholders only while surrounding prose is translated.
- Formula detection covers TeX and common math fonts plus monospace/code families such as Consolas, Courier, Menlo, Monaco, Inconsolata, Source Code, Fira Code, DejaVu Sans Mono, and Liberation Mono.
- Isolated formulas, formula captions, figures, and tables remain protected layout regions.

## Numbered-page structures

- Table-of-contents detection covers headings, dot leaders, box-drawing leaders, wide spacing, em/en spaces, standalone page numbers, Roman numerals, and pages dominated by text-number endings.
- Index detection covers an `Index` heading and term-to-page-number rows.
- Nomenclature, notation, symbol, abbreviation, and glossary pages preserve alternating symbol-definition structures.
- Reference and bibliography pages preserve numbered, bracketed, author-year, DOI, ISBN, ISSN, and URL-heavy citation structures.

These classifications preserve the complete page layout instead of reflowing numbers into translated prose.

## Vietnamese typesetting

- Vietnamese text uses a `1.2` line-height multiplier.
- Windows uses Times New Roman when available; other environments use the downloaded Unicode font fallback.
- Long translations scale down before rendering, wrap at word boundaries, reduce line height when necessary, and shrink again only when the paragraph still exceeds its original box.
- Extended bullets remain anchored, and vertically separated list items start new paragraphs.

## Scan and source safety

- A rendered image covering more than half the page marks the page as scanned; translated text regions receive white backing rectangles so source pixels do not show through.
- The core does not perform OCR. A scan without an extractable text layer remains untranslated.
- Structural PDF repair uses a temporary copy. The source file is never overwritten.
- The translated PDF retains the source page canvas and page count; a requested page subset limits translation rather than removing pages.

## Known limits

Text inside a protected table or figure can remain in the source language. Complex embedded fonts, malformed content streams, or inaccurate layout-model classifications can also require manual review. Treat any substantial untranslated passage or visual defect as a partial result.
