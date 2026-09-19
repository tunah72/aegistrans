---
name: medical-dental-translation
description: Translate medical/dental textbooks from English to Vietnamese with accurate terminology for Dentistry, Oral Medicine, TMD, and Occlusion. Provides system prompts, glossary, and translation rules for professional medical translation.
---

# Medical Dental Translation Skill

This skill provides resources for translating medical/dental textbooks from English to Vietnamese, specialized for:
- Temporomandibular Disorders (TMD)
- Occlusion
- Oral Medicine
- Dental Anatomy
- Orofacial Pain

## Components

| File | Purpose |
|------|--------|
| `system_prompt.txt` | LLM system prompt for medical translation |
| `glossary_base.jsonl` | Seed terminology glossary (60+ terms) |

## Usage

The system prompt is loaded automatically by the `openai` translation engine when `--system-prompt` points to it:

```bash
python scripts/translate_pdf.py input.pdf --output-dir output/ --engine openai --system-prompt medical-dental-translation/system_prompt.txt
```

Or for book-level translation:

```bash
python scripts/translate_book.py books/your-book.pdf --output-dir output/your_book/ --system-prompt medical-dental-translation/system_prompt.txt --glossary medical-dental-translation/glossary_base.jsonl
```

## Terminology Strategy

### Group A — Standard Vietnamese translations
Terms with well-established Vietnamese equivalents. Translate directly.

Examples: mandible → xương hàm dưới, maxilla → xương hàm trên

### Group B — Keep English in parentheses on first use
Specialized terms that need the English reference for clarity.

Format: `Vietnamese term (English term)`

Example: rối loạn thái dương hàm (temporomandibular disorders – TMD)

### Group C — Ambiguous terms
Terms where Vietnamese translation could cause confusion. Always include English.

Format: `Vietnamese term (English term)`

## Translation Rules

1. **No word-by-word translation** — translate by meaning and medical concept
2. **No added knowledge** — do not explain, infer, or add clinical recommendations
3. **No information loss** — do not summarize, shorten, or omit
4. **Preserve all numbers, units, measurements** exactly
5. **Preserve figure/table numbering** (Figure 3-2 → Hình 3-2)
6. **Preserve citations and references** unchanged
7. **Do not translate** author names, drug names, device names, proper nouns
8. **Preserve formula placeholders** `<b0></b0>` exactly as-is
