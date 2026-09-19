#!/usr/bin/env python3
"""Merge multiple chapter PDFs into a single final PDF with preserved bookmark outline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
import fitz  # PyMuPDF


def merge_pdfs(pdf_paths: list[Path], output_pdf: Path) -> int:
    """Merge a sequence of PDFs into one document, building TOC entries."""
    if not pdf_paths:
        print("Error: No PDFs provided to merge.", file=sys.stderr)
        return 1

    merged = fitz.open()
    toc = []
    current_page = 1

    for idx, path in enumerate(pdf_paths, 1):
        if not path.is_file():
            print(f"Warning: Skipping missing file {path}", file=sys.stderr)
            continue

        doc = fitz.open(path)
        page_count = doc.page_count
        title = path.stem.replace("_", " ")

        # Add top-level TOC entry for this chapter/part
        toc.append([1, title, current_page])

        # Import sub-TOC if present
        sub_toc = doc.get_toc()
        for item in sub_toc:
            lvl, sub_title, page_num = item
            toc.append([lvl + 1, sub_title, current_page + page_num - 1])

        merged.insert_pdf(doc)
        current_page += page_count
        doc.close()
        print(f"Merged: {path.name} ({page_count} pages, now at page {current_page - 1})")

    merged.set_toc(toc)
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    merged.save(output_pdf, deflate=True, garbage=3)
    merged.close()

    print(f"\nSuccessfully generated merged PDF: {output_pdf}")
    print(f"Total pages: {current_page - 1}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge translated chapter PDFs into one book.")
    parser.add_argument("input_pdfs", nargs="+", type=Path, help="Chapter PDFs in order")
    parser.add_argument("--output", type=Path, required=True, help="Output merged PDF path")
    args = parser.parse_args()

    return merge_pdfs([p.expanduser().resolve() for p in args.input_pdfs], args.output.expanduser().resolve())


if __name__ == "__main__":
    raise SystemExit(main())
