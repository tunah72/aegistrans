#!/usr/bin/env python3
"""Split a large PDF into chapter-sized PDFs based on the Table of Contents."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
import fitz  # PyMuPDF


def extract_chapters_from_pdf(
    input_pdf: Path,
    output_dir: Path,
    *,
    min_pages: int = 1,
) -> list[dict]:
    """Inspect TOC and split input PDF into individual chapter PDF files."""
    doc = fitz.open(input_pdf)
    total_pages = doc.page_count
    toc = doc.get_toc()

    output_dir.mkdir(parents=True, exist_ok=True)

    # Filter TOC items that represent major sections or chapters
    # Patterns like "1 - Functional Anatomy", "Chapter 1", "Section I", etc.
    major_entries = []
    for item in toc:
        lvl, title, page = item
        clean_title = title.strip().replace("\r", " ").replace("\n", " ")
        # Check if title looks like a chapter or major section
        if lvl in (1, 2):
            major_entries.append((lvl, clean_title, page))

    if not major_entries:
        print("No chapter-level TOC entries found. Splitting by page blocks instead.")
        return []

    # Filter to chapters specifically
    chapters = []
    for i, (lvl, title, start_page) in enumerate(major_entries):
        is_chapter = bool(
            re.match(r"^\d+\s*[-–]\s*", title)
            or re.match(r"^Chapter\s+\d+", title, re.IGNORECASE)
        )
        is_index = bool(re.match(r"^Index\b", title, re.IGNORECASE))
        if is_chapter or is_index:
            chapters.append({"title": title, "start_page": start_page})

    # Deduplicate by start page
    unique_chapters = []
    seen_pages = set()
    for c in chapters:
        if c["start_page"] not in seen_pages and 1 <= c["start_page"] <= total_pages:
            unique_chapters.append(c)
            seen_pages.add(c["start_page"])

    unique_chapters.sort(key=lambda x: x["start_page"])

    # Prepend Front Matter if the first chapter does not begin on page 1
    if unique_chapters and unique_chapters[0]["start_page"] > 1:
        unique_chapters.insert(0, {
            "title": "Front Matter",
            "start_page": 1,
        })

    # Determine end pages
    results = []
    for idx, c in enumerate(unique_chapters):
        start = c["start_page"]
        if idx + 1 < len(unique_chapters):
            end = unique_chapters[idx + 1]["start_page"] - 1
        else:
            end = total_pages

        if end < start:
            end = start

        # Safe filename
        safe_name = re.sub(r"[^\w\-.]", "_", c["title"])[:50]
        filename = f"{idx + 1:02d}_{safe_name}_p{start}-{end}.pdf"
        out_path = output_dir / filename

        # Create sub-PDF
        sub_doc = fitz.open()
        sub_doc.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
        sub_doc.save(out_path)
        sub_doc.close()

        c_info = {
            "index": idx + 1,
            "title": c["title"],
            "start_page": start,
            "end_page": end,
            "page_count": end - start + 1,
            "path": str(out_path),
        }
        results.append(c_info)
        print(f"[{idx + 1:02d}] {c['title']} (Pages {start}-{end}, {end - start + 1}p) -> {out_path.name}")

    doc.close()
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Split PDF into chapters.")
    parser.add_argument("input_pdf", type=Path, help="Source PDF")
    parser.add_argument("--output-dir", type=Path, default=Path("books/chapters"),
                        help="Output directory for chapters")
    args = parser.parse_args()

    input_pdf = args.input_pdf.expanduser().resolve()
    if not input_pdf.is_file():
        print(f"Error: {input_pdf} not found.", file=sys.stderr)
        return 1

    chapters = extract_chapters_from_pdf(input_pdf, args.output_dir.expanduser().resolve())
    print(f"\nExtracted {len(chapters)} chapters to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
