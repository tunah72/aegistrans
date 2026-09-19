#!/usr/bin/env python3
"""Batch translate all chapters and merge into the final Vietnamese textbook."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from scripts.merge_pdfs import merge_pdfs


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Batch translate all textbook chapters and merge final PDF."
    )
    parser.add_argument(
        "--chapters-dir",
        type=Path,
        default=SKILL_ROOT / "books" / "chapters",
        help="Directory containing split chapter PDFs (default: books/chapters)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SKILL_ROOT / "output" / "chapters",
        help="Base output directory for chapters (default: output/chapters)",
    )
    parser.add_argument(
        "--final-pdf",
        type=Path,
        default=SKILL_ROOT / "output" / "OKESON_8th_Edition_Vietnamese.pdf",
        help="Final merged PDF path (default: output/OKESON_8th_Edition_Vietnamese.pdf)",
    )
    parser.add_argument(
        "--profile",
        type=str,
        default="dental",
        help="Medical profile name ('dental', 'general_medicine') or path (default: dental)",
    )
    parser.add_argument(
        "--system-prompt",
        type=Path,
        default=None,
        help="Path to system prompt file (defaults to profile prompt)",
    )
    parser.add_argument(
        "--glossary",
        type=Path,
        default=None,
        help="Path to glossary file (defaults to profile glossary)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Translation concurrency (default: 2)",
    )
    parser.add_argument(
        "--start-chapter",
        type=int,
        default=1,
        help="Chapter index to start from (1-based, default: 1)",
    )
    parser.add_argument(
        "--end-chapter",
        type=int,
        default=999,
        help="Chapter index to end at (inclusive)",
    )
    parser.add_argument(
        "--skip-merge",
        action="store_true",
        help="Only translate chapters, do not merge final PDF",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    chapters_dir = args.chapters_dir.resolve()
    base_output = args.output_dir.resolve()
    base_output.mkdir(parents=True, exist_ok=True)

    if not chapters_dir.is_dir():
        print(f"Error: Chapters directory not found: {chapters_dir}", file=sys.stderr)
        return 1

    chapter_files = sorted([f for f in chapters_dir.glob("*.pdf")])
    if not chapter_files:
        print(f"Error: No PDF files found in {chapters_dir}", file=sys.stderr)
        return 1

    total_chapters = len(chapter_files)
    print("=" * 65)
    print(f"BATCH TEXTBOOK TRANSLATION: {total_chapters} chapters discovered")
    print(f"Profile:          {args.profile}")
    print(f"Output Directory: {base_output}")
    if args.system_prompt:
        print(f"System Prompt:    {args.system_prompt}")
    if args.glossary:
        print(f"Glossary:         {args.glossary}")
    print("=" * 65)

    translated_pdfs = []
    start_total_time = time.time()

    for idx, chapter_pdf in enumerate(chapter_files, start=1):
        if idx < args.start_chapter or idx > args.end_chapter:
            continue

        ch_name = chapter_pdf.stem
        ch_output = base_output / ch_name
        ch_output.mkdir(parents=True, exist_ok=True)

        print(f"\n>>> [{idx}/{total_chapters}] Translating: {chapter_pdf.name}")
        ch_start = time.time()

        cmd = [
            sys.executable,
            str(SKILL_ROOT / "scripts" / "translate_book.py"),
            str(chapter_pdf),
            "--output-dir",
            str(ch_output),
            "--profile",
            str(args.profile),
            "--concurrency",
            str(args.concurrency),
        ]
        if args.system_prompt:
            cmd.extend(["--system-prompt", str(args.system_prompt)])
        if args.glossary:
            cmd.extend(["--glossary", str(args.glossary)])

        result = subprocess.run(cmd)
        ch_elapsed = time.time() - ch_start

        if result.returncode != 0:
            print(
                f"ERROR: Failed translating chapter {idx} ({chapter_pdf.name}) with code {result.returncode}",
                file=sys.stderr,
            )
            return result.returncode

        # Locate translated output PDF
        out_candidates = list(ch_output.glob("*-vi.pdf"))
        if out_candidates:
            translated_pdfs.append(out_candidates[0])
            print(f"✓ [{idx}/{total_chapters}] Done in {ch_elapsed:.0f}s -> {out_candidates[0].name}")
        else:
            print(f"Warning: No -vi.pdf found in {ch_output}", file=sys.stderr)

    total_elapsed = time.time() - start_total_time
    print("\n" + "=" * 65)
    print(f"ALL CHAPTERS TRANSLATED in {total_elapsed / 60:.1f} minutes")
    print("=" * 65)

    if not args.skip_merge and translated_pdfs:
        print("\n>>> Merging all translated chapters into final textbook...")
        merge_res = merge_pdfs(translated_pdfs, args.final_pdf.resolve())
        if merge_res == 0:
            print(f"\n★ FINAL BOOK READY: {args.final_pdf.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
