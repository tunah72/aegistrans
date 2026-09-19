#!/usr/bin/env python3
"""Translate an entire textbook PDF with checkpoint/resume support.

This orchestrator:
1. Extracts translatable segments from the PDF (handoff pass 1)
2. Translates each segment via an OpenAI-compatible LLM
3. Saves progress to a checkpoint database
4. Rebuilds the translated PDF (handoff pass 2)

Supports resuming after interruption — only untranslated segments
are retried on the next run.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(SKILL_ROOT / ".env")
except ImportError:
    pass

from scripts.translate_pdf import (
    TranslationError,
    translate_pdf,
    _use_utf8_output,
)
from pdf2zh.profiles import list_available_profiles, load_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("translate_book")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Translate a textbook PDF with checkpoint/resume support."
    )
    parser.add_argument("input_pdf", type=Path, help="Path to the source PDF")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Directory for all output files")
    available = ", ".join(list_available_profiles(SKILL_ROOT)) or "dental, general_medicine"
    parser.add_argument("--profile", type=str, default="dental",
                        help=f"Medical profile name (available: {available}) or path (default: dental)")
    parser.add_argument("--system-prompt", type=Path,
                        help="Path to a system prompt file for translation")
    parser.add_argument("--glossary", type=Path,
                        help="Path to a JSONL glossary file")
    parser.add_argument("--pages", type=str, default=None,
                        help="Page range to translate, e.g. 1-10,15-20")
    parser.add_argument("--concurrency", type=int, default=2,
                        help="Number of concurrent translation threads (default: 2)")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="Maximum retries per failed segment (default: 3)")
    parser.add_argument("--request-interval", type=float, default=0.5,
                        help="Minimum seconds between API requests (default: 0.5)")
    parser.add_argument("--batch-size", type=int, default=50,
                        help="Number of segments per checkpoint save (default: 50)")
    parser.add_argument("--skip-rebuild", action="store_true",
                        help="Only translate segments, don't rebuild PDF")
    parser.add_argument("--force-retranslate", action="store_true",
                        help="Re-translate all segments, ignoring checkpoint")
    parser.add_argument("--overwrite", action="store_true",
                        help="Overwrite existing output PDF")
    parser.add_argument("--target-language", default="vi",
                        help="Target language code (default: vi)")
    parser.add_argument("--source-language", default="auto",
                        help="Source language code (default: auto)")
    parser.add_argument("--threads", type=int, default=4,
                        help="PDF processing threads (default: 4)")
    return parser.parse_args(argv)


def step_extract_segments(
    input_pdf: Path,
    output_dir: Path,
    segments_path: Path,
    target_language: str = "vi",
    source_language: str = "auto",
    pages: str | None = None,
    threads: int = 4,
    overwrite: bool = False,
) -> int:
    """Extract translatable segments from PDF using handoff engine pass 1."""
    logger.info("=== Step 1: Extracting segments from %s ===", input_pdf.name)

    if segments_path.exists() and not overwrite:
        count = sum(1 for line in segments_path.open(encoding="utf-8") if line.strip())
        if count > 0:
            logger.info("Segments file already exists with %d segments, reusing", count)
            return count

    translate_pdf(
        input_pdf,
        output_dir=None,  # No PDF output during extraction
        target_language=target_language,
        source_language=source_language,
        pages=pages,
        threads=threads,
        engine="handoff",
        emit_segments=segments_path,
        overwrite=True,
    )

    count = sum(1 for line in segments_path.open(encoding="utf-8") if line.strip())
    logger.info("Extracted %d segments", count)
    return count


def step_translate_segments(
    segments_path: Path,
    output_dir: Path,
    translations_path: Path,
    checkpoint_path: Path,
    *,
    system_prompt: Path | None = None,
    glossary: Path | None = None,
    concurrency: int = 2,
    max_retries: int = 3,
    request_interval: float = 0.5,
    batch_size: int = 50,
    force_retranslate: bool = False,
) -> dict:
    """Translate segments via OpenAI-compatible LLM with checkpointing."""
    from pdf2zh.checkpoint import TranslationCheckpoint
    from pdf2zh.validation import validate_translation

    logger.info("=== Step 2: Translating segments ===")

    # Load segments
    segments = []
    with open(segments_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                record = json.loads(line)
                segments.append(record["src"])

    if not segments:
        logger.warning("No segments to translate")
        return {"total": 0, "completed": 0, "failed": 0}

    logger.info("Total segments: %d", len(segments))

    # Initialize checkpoint
    checkpoint = TranslationCheckpoint(checkpoint_path)

    if force_retranslate:
        # Remove existing checkpoint data
        checkpoint._conn.execute("DELETE FROM segments")
        checkpoint._conn.commit()

    checkpoint.load_segments(segments)
    checkpoint.set_metadata("source_file", str(segments_path))
    checkpoint.set_metadata("model", os.environ.get("LLM_MODEL", "unknown"))

    # Check existing progress
    stats = checkpoint.get_stats()
    if stats.get("completed", 0) > 0:
        logger.info(
            "Resuming: %d/%d already completed, %d failed",
            stats.get("completed", 0), stats["total"], stats.get("failed", 0),
        )

    # Get pending segments
    pending = checkpoint.get_pending(max_retries=max_retries)
    if not pending:
        logger.info("All segments already translated!")
        checkpoint.export_translations(translations_path)
        total_stats = checkpoint.get_stats()
        checkpoint.close()
        return total_stats

    logger.info("Segments to translate: %d", len(pending))

    # Initialize OpenAI translator
    from pdf2zh.translator import OpenAITranslator, remove_control_characters

    envs = {"request_interval": str(request_interval)}
    if system_prompt and system_prompt.is_file():
        envs["system_prompt"] = str(system_prompt.resolve())
    if glossary and glossary.is_file():
        envs["glossary"] = str(glossary.resolve())

    translator = OpenAITranslator(
        lang_in="en",
        lang_out="vi",
        envs=envs,
        ignore_cache=True,  # We use our own checkpoint
    )

    # Setup logging
    log_path = output_dir / "translation.log"
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-5s %(message)s", datefmt="%H:%M:%S"
    ))
    logger.addHandler(file_handler)

    # Validation log
    validation_log = output_dir / "validation.log"

    # Translate with batching
    translated_count = 0
    failed_count = 0
    start_time = time.time()

    for batch_start in range(0, len(pending), batch_size):
        batch = pending[batch_start:batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        total_batches = (len(pending) + batch_size - 1) // batch_size

        logger.info(
            "Batch %d/%d (%d segments)",
            batch_num, total_batches, len(batch),
        )

        for seg in batch:
            seg_id = seg.segment_id
            source = seg.source_text

            # Skip very short segments (single chars, whitespace)
            if not source.strip() or len(source.strip()) < 2:
                checkpoint.mark_completed(seg_id, source, model="skip")
                translated_count += 1
                continue

            try:
                translation = translator.do_translate(source)

                # Validate
                vresult = validate_translation(seg_id, source, translation)
                if vresult.errors:
                    # Critical validation failure
                    error_msg = "; ".join(vresult.errors)
                    logger.warning("Segment %d validation error: %s", seg_id, error_msg)
                    checkpoint.mark_failed(seg_id, f"validation: {error_msg}")
                    failed_count += 1

                    with open(validation_log, "a", encoding="utf-8") as vf:
                        vf.write(f"SEGMENT {seg_id} ERROR: {error_msg}\n")
                        vf.write(f"  SOURCE: {source[:200]}\n")
                        vf.write(f"  TRANSLATION: {translation[:200]}\n\n")
                    continue

                if vresult.warnings:
                    with open(validation_log, "a", encoding="utf-8") as vf:
                        for w in vresult.warnings:
                            vf.write(f"SEGMENT {seg_id} WARNING: {w}\n")

                checkpoint.mark_completed(
                    seg_id, translation,
                    model=translator.model or "",
                )
                translated_count += 1

                if translated_count % 10 == 0:
                    elapsed = time.time() - start_time
                    rate = translated_count / elapsed if elapsed > 0 else 0
                    logger.info(
                        "Progress: %d/%d translated (%.1f seg/min), %d failed",
                        translated_count, len(pending), rate * 60, failed_count,
                    )

            except KeyboardInterrupt:
                logger.info("Interrupted! Progress saved to checkpoint.")
                break
            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                logger.error("Segment %d failed: %s", seg_id, error_msg)
                checkpoint.mark_failed(seg_id, error_msg)
                failed_count += 1

                # Exponential backoff on failure
                backoff = min(2 ** seg.retry_count, 30)
                logger.info("Backing off %ds after failure", backoff)
                time.sleep(backoff)

    # Export completed translations
    exported = checkpoint.export_translations(translations_path)
    logger.info("Exported %d translations to %s", exported, translations_path)

    final_stats = checkpoint.get_stats()
    elapsed = time.time() - start_time
    logger.info(
        "Translation complete in %.0fs: %s",
        elapsed, json.dumps(final_stats),
    )

    checkpoint.close()
    logger.removeHandler(file_handler)
    return final_stats


def step_rebuild_pdf(
    input_pdf: Path,
    output_dir: Path,
    translations_path: Path,
    still_missing_path: Path,
    *,
    target_language: str = "vi",
    source_language: str = "auto",
    pages: str | None = None,
    threads: int = 4,
    overwrite: bool = False,
) -> Path | None:
    """Rebuild the translated PDF using handoff engine pass 2."""
    logger.info("=== Step 3: Rebuilding translated PDF ===")

    if not translations_path.exists():
        logger.error("Translations file not found: %s", translations_path)
        return None

    count = sum(1 for line in translations_path.open(encoding="utf-8") if line.strip())
    logger.info("Using %d translations for rebuild", count)

    result = translate_pdf(
        input_pdf,
        output_dir=output_dir,
        target_language=target_language,
        source_language=source_language,
        pages=pages,
        threads=threads,
        engine="handoff",
        segments=translations_path,
        emit_segments=still_missing_path,
        overwrite=overwrite,
    )

    if result.path:
        logger.info("Translated PDF: %s", result.path)
        if result.untranslated:
            logger.warning("%d segments still untranslated", result.untranslated)

            # Count remaining
            if still_missing_path.exists():
                remaining = sum(
                    1 for line in still_missing_path.open(encoding="utf-8")
                    if line.strip()
                )
                logger.warning(
                    "Still missing segments written to: %s (%d segments)",
                    still_missing_path, remaining,
                )
    else:
        logger.error("No output PDF was generated")

    return result.path


def main(argv=None) -> int:
    _use_utf8_output()
    args = _parse_args(argv)

    input_pdf = args.input_pdf.expanduser().resolve()
    if not input_pdf.is_file():
        print(f"error: Input PDF does not exist: {input_pdf}", file=sys.stderr)
        return 2

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # File paths
    segments_path = output_dir / "segments.jsonl"
    translations_path = output_dir / "translations.jsonl"
    checkpoint_path = output_dir / "checkpoint.db"
    still_missing_path = output_dir / "still_missing.jsonl"

    # Resolve profile defaults if system_prompt or glossary not explicitly given
    profile_assets = None
    if args.profile:
        profile_assets = load_profile(args.profile, root=SKILL_ROOT)
        if not profile_assets:
            available = ", ".join(list_available_profiles(SKILL_ROOT))
            logger.warning(
                "Profile '%s' not found. Available profiles in medical-translation/profiles/: [%s]",
                args.profile, available,
            )

    system_prompt = args.system_prompt
    if not system_prompt and profile_assets and profile_assets.system_prompt:
        system_prompt = profile_assets.system_prompt

    glossary = args.glossary
    if not glossary and profile_assets and profile_assets.glossary:
        glossary = profile_assets.glossary

    logger.info("=" * 60)
    logger.info("Book Translation Pipeline")
    logger.info("Input: %s", input_pdf)
    logger.info("Output: %s", output_dir)
    logger.info("Profile: %s (%s)", args.profile, profile_assets.dir_path if profile_assets else "custom/none")
    logger.info("System Prompt: %s", system_prompt)
    logger.info("Glossary: %s", glossary)
    logger.info("Model: %s", os.environ.get("LLM_MODEL", "default"))
    logger.info("=" * 60)

    if args.force_retranslate:
        if segments_path.exists():
            segments_path.unlink()
        if translations_path.exists():
            translations_path.unlink()
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    try:
        # Step 1: Extract segments
        segment_count = step_extract_segments(
            input_pdf, output_dir, segments_path,
            target_language=args.target_language,
            source_language=args.source_language,
            pages=args.pages,
            threads=args.threads,
            overwrite=args.overwrite or args.force_retranslate,
        )

        if segment_count == 0:
            logger.error("No segments extracted from PDF")
            return 1

        # Step 2: Translate segments
        stats = step_translate_segments(
            segments_path, output_dir, translations_path, checkpoint_path,
            system_prompt=system_prompt,
            glossary=glossary,
            concurrency=args.concurrency,
            max_retries=args.max_retries,
            request_interval=args.request_interval,
            batch_size=args.batch_size,
            force_retranslate=args.force_retranslate,
        )

        logger.info("Translation stats: %s", json.dumps(stats))

        if args.skip_rebuild:
            logger.info("Skipping PDF rebuild (--skip-rebuild)")
            return 0

        # Step 3: Rebuild PDF
        result_path = step_rebuild_pdf(
            input_pdf, output_dir, translations_path, still_missing_path,
            target_language=args.target_language,
            source_language=args.source_language,
            pages=args.pages,
            threads=args.threads,
            overwrite=args.overwrite,
        )

        # Final report
        logger.info("=" * 60)
        logger.info("TRANSLATION COMPLETE")
        logger.info("Total segments: %d", stats.get("total", 0))
        logger.info("Completed: %d", stats.get("completed", 0))
        logger.info("Failed: %d", stats.get("failed", 0))
        if result_path:
            logger.info("Output PDF: %s", result_path)
        logger.info("Checkpoint: %s", checkpoint_path)
        logger.info("Translations: %s", translations_path)
        logger.info("=" * 60)

        return 0

    except TranslationError as e:
        logger.error("Translation error: %s", e)
        return 2
    except KeyboardInterrupt:
        logger.info("Interrupted. Progress saved to checkpoint. Run again to resume.")
        return 130
    except Exception as e:
        logger.exception("Unexpected error: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
