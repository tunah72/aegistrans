---
name: aegistrans
description: >-
  Translate local PDFs and massive medical or scientific textbooks into Vietnamese
  with strict layout preservation, dual-language terminology retention (e.g. Thuật ngữ (English term)),
  modular specialty profiles (dental, general_medicine), and fault-tolerant SQLite checkpointing.
  Use when the user wants to translate medical books, dental textbooks, or academic PDFs, split textbooks
  by chapters, resume interrupted translations, or configure LLM translation gateways.
---

# AegisTrans: Medical & Scientific PDF Translation Skill

Translate medical, dental, and academic PDFs while preserving exact publisher typography, equations, tables, figures, and bookmarks. Supports bilingual terminology retention `Thuật ngữ (English term)` and SQLite checkpoint resumption.

## 1. Prerequisites & Environment Setup

Resolve the absolute repository root path before running commands:
- **Python Interpreter**: `<repo-root>/.venv/bin/python`
- **Dependencies**: Ensure `<repo-root>/.venv` is installed with `pip install -r requirements.txt`.
- **API Credentials**: If using an LLM engine, ensure `.env` exists in the repository root (see `.env.example`):
  ```env
  OPENAI_BASE_URL=http://localhost:20128/v1
  OPENAI_API_KEY=your_key_here
  LLM_MODEL=ag/gemini-3.8-flash-low
  ```

---

## 2. Workflows & Translation Modes

### Mode 1: Medical Textbook Translation (Recommended for Books & Chapters)
Translates through an OpenAI-compatible gateway with dual-language terminology retention and SQLite checkpointing:

```bash
<python> scripts/translate_book.py <input.pdf> \
    --output-dir <output-dir> \
    --profile <profile-name> \
    --concurrency 2
```

**Available Specialty Profiles**:
- `dental`: Dentistry, TMD, Occlusion, Craniofacial anatomy.
- `general_medicine`: Internal Medicine, Surgery, Physiology, Pathology, Pharmacology.
- *Custom*: Place any new specialty profile under `medical-translation/profiles/<name>/`.

**Key Flags**:
- `--profile <name>`: Automatically loads `system_prompt.txt` and `glossary_base.jsonl`.
- `--pages <range>`: Restrict pages (e.g. `1-10,15-20`).
- `--concurrency <N>`: Number of parallel translation workers (default: 2).
- `--force-retranslate`: Clear checkpoint and re-translate from scratch.

### Mode 2: Multi-Chapter Textbook Pipeline (For 200–800+ Page Textbooks)
For full-length textbooks, use the split-translate-merge pipeline:

1. **Split into chapter PDFs based on PDF bookmarks**:
   ```bash
   <python> scripts/split_pdf_by_chapters.py <book.pdf> --output-dir <chapters-dir>
   ```

2. **Batch translate all chapters and merge into final book**:
   ```bash
   <python> scripts/translate_all_chapters.py \
       --chapters-dir <chapters-dir> \
       --output-dir <output-dir> \
       --final-pdf <final.pdf> \
       --profile <profile-name> \
       --concurrency 2
   ```

### Mode 3: Rapid Draft via Google Translate (Zero-Config)
For quick document translation without API keys:
```bash
<python> scripts/translate_pdf.py <input.pdf> --output-dir <output-dir> --target-language vi
```

### Mode 4: Agent Handoff Mode
Extracts translatable text segments to JSONL for the active agent to translate directly:
1. **Extract segments**:
   ```bash
   <python> scripts/translate_pdf.py <input.pdf> --engine handoff --emit-segments segments.jsonl
   ```
2. **Translate JSONL**: Translate `src` to `dst` while preserving `<b0></b0>` formula tags.
3. **Rebuild PDF**:
   ```bash
   <python> scripts/translate_pdf.py <input.pdf> --engine handoff --segments translations.jsonl --output-dir <output-dir>
   ```

---

## 3. Essential Rules for Medical Translation

1. **Bilingual Terminology Format**: Format specialized clinical terms as `Thuật ngữ tiếng Việt (English term)` (e.g. `xương hàm dưới (mandible)`, `khớp thái dương hàm (temporomandibular joint – TMJ)`).
2. **Immutable Placeholders**: Never alter or drop `<b0>`, `</b0>` or other formula tags.
3. **Preserve Structure**: Keep table and figure numbers (e.g. `Hình 1.1`), URLs, and citations unchanged.
4. **No Hallucination**: Do not add unverified clinical recommendations or commentary.

---

## 4. Quality Verification Checklist

1. Confirm the output PDF exists and the source file is unchanged.
2. Confirm source and output page counts match.
3. Check text extraction for untranslated passages, corrupted placeholders, or broken layouts.
4. When page rendering is available, verify typography, heading colors, and multi-column alignment.
