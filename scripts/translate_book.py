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
) -> tuple[int, float, bool]:
    """Extract translatable segments from PDF using handoff engine pass 1.

    Returns (segment_count, elapsed_seconds, was_cached).
    """
    logger.info("=== Step 1: Extracting segments from %s ===", input_pdf.name)
    t0 = time.perf_counter()

    if segments_path.exists() and not overwrite:
        count = sum(1 for line in segments_path.open(encoding="utf-8") if line.strip())
        if count > 0:
            elapsed = time.perf_counter() - t0
            logger.info("Segments file already exists with %d segments, reusing (%.2fs)", count, elapsed)
            return count, elapsed, True

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

    elapsed = time.perf_counter() - t0
    count = sum(1 for line in segments_path.open(encoding="utf-8") if line.strip())
    logger.info("Extracted %d segments in %.2fs", count, elapsed)
    return count, elapsed, False


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
) -> tuple[dict, float]:
    """Translate segments via OpenAI-compatible LLM with checkpointing.

    Returns (stats_dict, elapsed_seconds).
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from pdf2zh.checkpoint import TranslationCheckpoint
    from pdf2zh.validation import validate_translation

    logger.info("=== Step 2: Translating segments ===")
    t0 = time.perf_counter()

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
        return {"total": 0, "completed": 0, "failed": 0}, time.perf_counter() - t0

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
        elapsed = time.perf_counter() - t0
        return total_stats, elapsed

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

    val_lock = threading.Lock()
    counter_lock = threading.Lock()
    translated_count = 0
    failed_count = 0
    total_pending = len(pending)
    start_time = time.perf_counter()

    def _translate_one(seg) -> tuple[str, int, str | None]:
        nonlocal translated_count, failed_count
        seg_id = seg.segment_id
        source = seg.source_text

        # Skip very short segments (single chars, whitespace)
        if not source.strip() or len(source.strip()) < 2:
            checkpoint.mark_completed(seg_id, source, model="skip")
            with counter_lock:
                translated_count += 1
            return "skipped", seg_id, None

        retries = 0
        while retries <= max_retries:
            try:
                translation = translator.do_translate(source)

                # Validate
                vresult = validate_translation(seg_id, source, translation)
                if vresult.errors:
                    error_msg = "; ".join(vresult.errors)
                    logger.warning("Segment %d validation error: %s", seg_id, error_msg)
                    checkpoint.mark_failed(seg_id, f"validation: {error_msg}")
                    with val_lock:
                        with open(validation_log, "a", encoding="utf-8") as vf:
                            vf.write(f"SEGMENT {seg_id} ERROR: {error_msg}\n")
                            vf.write(f"  SOURCE: {source[:200]}\n")
                            vf.write(f"  TRANSLATION: {translation[:200]}\n\n")
                    with counter_lock:
                        failed_count += 1
                    return "failed", seg_id, error_msg

                if vresult.warnings:
                    with val_lock:
                        with open(validation_log, "a", encoding="utf-8") as vf:
                            for w in vresult.warnings:
                                vf.write(f"SEGMENT {seg_id} WARNING: {w}\n")

                checkpoint.mark_completed(
                    seg_id, translation,
                    model=translator.model or "",
                )
                with counter_lock:
                    translated_count += 1
                return "completed", seg_id, None

            except KeyboardInterrupt:
                raise
            except Exception as e:
                error_msg = f"{type(e).__name__}: {e}"
                retries += 1
                if retries <= max_retries:
                    backoff = min(2 ** retries, 15)
                    logger.warning(
                        "Segment %d failed (attempt %d/%d): %s. Backing off %ds...",
                        seg_id, retries, max_retries, error_msg, backoff,
                    )
                    time.sleep(backoff)
                else:
                    logger.error("Segment %d failed after %d retries: %s", seg_id, max_retries, error_msg)
                    checkpoint.mark_failed(seg_id, error_msg)
                    with counter_lock:
                        failed_count += 1
                    return "failed", seg_id, error_msg
        return "failed", seg_id, "exhausted retries"

    logger.info(
        "Translating %d segments (concurrency=%d, request_interval=%.2fs)...",
        total_pending, concurrency, request_interval,
    )

    try:
        if concurrency > 1:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                futures = {executor.submit(_translate_one, seg): seg for seg in pending}
                for future in as_completed(futures):
                    try:
                        future.result()
                    except KeyboardInterrupt:
                        logger.info("Interrupted! Cancelling pending tasks...")
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                    with counter_lock:
                        done = translated_count + failed_count
                        cur_trans = translated_count
                        cur_fail = failed_count

                    if done % 10 == 0 or done == total_pending:
                        elapsed_so_far = time.perf_counter() - start_time
                        rate = done / elapsed_so_far if elapsed_so_far > 0 else 0
                        remaining = total_pending - done
                        eta = (remaining / rate) if rate > 0 else 0
                        logger.info(
                            "Progress: %d/%d processed (%d ok, %d fail) | Rate: %.1f seg/min | Elapsed: %.1fs | ETA: %.0fs",
                            done, total_pending, cur_trans, cur_fail, rate * 60, elapsed_so_far, eta,
                        )
        else:
            for seg in pending:
                _translate_one(seg)
                with counter_lock:
                    done = translated_count + failed_count
                    cur_trans = translated_count
                    cur_fail = failed_count

                if done % 10 == 0 or done == total_pending:
                    elapsed_so_far = time.perf_counter() - start_time
                    rate = done / elapsed_so_far if elapsed_so_far > 0 else 0
                    remaining = total_pending - done
                    eta = (remaining / rate) if rate > 0 else 0
                    logger.info(
                        "Progress: %d/%d processed (%d ok, %d fail) | Rate: %.1f seg/min | Elapsed: %.1fs | ETA: %.0fs",
                        done, total_pending, cur_trans, cur_fail, rate * 60, elapsed_so_far, eta,
                    )
    except KeyboardInterrupt:
        logger.info("Interrupted! Progress saved to checkpoint.")

    # Export completed translations
    exported = checkpoint.export_translations(translations_path)
    logger.info("Exported %d translations to %s", exported, translations_path)

    final_stats = checkpoint.get_stats()
    elapsed = time.perf_counter() - t0
    logger.info(
        "Translation step finished in %.2fs: %s",
        elapsed, json.dumps(final_stats),
    )

    checkpoint.close()
    logger.removeHandler(file_handler)
    return final_stats, elapsed


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
) -> tuple[Path | None, float]:
    """Rebuild the translated PDF using handoff engine pass 2.

    Returns (output_pdf_path, elapsed_seconds).
    """
    logger.info("=== Step 3: Rebuilding translated PDF ===")
    t0 = time.perf_counter()

    if not translations_path.exists():
        logger.error("Translations file not found: %s", translations_path)
        return None, time.perf_counter() - t0

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

    elapsed = time.perf_counter() - t0
    if result.path:
        logger.info("Translated PDF: %s (generated in %.2fs)", result.path, elapsed)
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
        logger.error("No output PDF was generated (elapsed: %.2fs)", elapsed)

    return result.path, elapsed


def main(argv=None) -> int:
    _use_utf8_output()
    total_start = time.perf_counter()
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
    logger.info("Concurrency: %d (request interval: %.2fs)", args.concurrency, args.request_interval)
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
        segment_count, t1_elapsed, cached = step_extract_segments(
            input_pdf, output_dir, segments_path,
            target_language=args.target_language,
            source_language=args.source_language,
            pages=args.pages,
            threads=args.threads,
            overwrite=args.overwrite or args.force_retranslate,
        )

        if segment_count == 0:
            logger.info("No translatable segments found (all pages preserved, e.g. index/diagrams). Preserving PDF...")
            dest_pdf = output_dir / f"{input_pdf.stem}-{args.target_language}.pdf"
            import shutil
            shutil.copyfile(input_pdf, dest_pdf)
            logger.info("Preserved PDF copied to: %s", dest_pdf)
            return 0

        # Step 2: Translate segments
        stats, t2_elapsed = step_translate_segments(
            segments_path, output_dir, translations_path, checkpoint_path,
            system_prompt=system_prompt,
            glossary=glossary,
            concurrency=args.concurrency,
            max_retries=args.max_retries,
            request_interval=args.request_interval,
            batch_size=args.batch_size,
            force_retranslate=args.force_retranslate,
        )

        if args.skip_rebuild:
            logger.info("Skipping PDF rebuild (--skip-rebuild)")
            total_elapsed = time.perf_counter() - total_start
            print(f"\n[Done] Step 2 complete in {t2_elapsed:.2f}s. Rebuild skipped.\n")
            return 0

        # Step 3: Rebuild PDF
        result_path, t3_elapsed = step_rebuild_pdf(
            input_pdf, output_dir, translations_path, still_missing_path,
            target_language=args.target_language,
            source_language=args.source_language,
            pages=args.pages,
            threads=args.threads,
            overwrite=args.overwrite,
        )

        total_elapsed = time.perf_counter() - total_start
        total_mins = int(total_elapsed // 60)
        total_secs = total_elapsed % 60

        completed = stats.get("completed", 0)
        failed = stats.get("failed", 0)
        total_seg = stats.get("total", segment_count)
        rate = (completed / t2_elapsed * 60) if t2_elapsed > 0 else 0

        p1 = (t1_elapsed / total_elapsed * 100) if total_elapsed > 0 else 0
        p2 = (t2_elapsed / total_elapsed * 100) if total_elapsed > 0 else 0
        p3 = (t3_elapsed / total_elapsed * 100) if total_elapsed > 0 else 0

        cache_str = "reused from cache" if cached else "extracted new"
        rebuild_str = f"{result_path.name}" if result_path else "Failed"

        timing_summary = [
            "",
            "=" * 74,
            "                 STAGE EXECUTION TIMING & PERFORMANCE SUMMARY",
            "=" * 74,
            f"  • Step 1: Segment Extraction   : {t1_elapsed:7.2f}s ({p1:5.1f}%)  [{segment_count} segments ({cache_str})]",
            f"  • Step 2: LLM Translation      : {t2_elapsed:7.2f}s ({p2:5.1f}%)  [{completed}/{total_seg} ok, {failed} fail, {rate:.1f} seg/min]",
            f"  • Step 3: PDF Rebuild & Layout : {t3_elapsed:7.2f}s ({p3:5.1f}%)  [{rebuild_str}]",
            "-" * 74,
            f"  • Total End-to-End Elapsed     : {total_elapsed:7.2f}s (100.0%)  [{total_mins}m {total_secs:04.1f}s total]",
            "=" * 74,
            "",
        ]
        for line in timing_summary:
            logger.info(line)
            print(line)

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
