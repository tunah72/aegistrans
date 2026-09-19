# AegisTrans Translation Rules

When processing, translating, or diagnosing medical and academic PDFs using AegisTrans:

1. **Dual-Language Terminology Learning Mode**:
   - Translate specialized clinical, anatomical, pharmacological, and biomechanical terms into standardized Vietnamese accompanied by their standard English reference in parentheses:
     $$\text{Thuật ngữ tiếng Việt (English term)}$$
     *(e.g., `xương hàm dưới (mandible)`, `khớp thái dương hàm (temporomandibular joint – TMJ)`, `dây chằng nha chu (periodontal ligament)`).*

2. **Strict Layout & Placeholder Preservation**:
   - Math and code formula placeholders such as `<b0></b0>` are strictly immutable. Every opening and closing tag must retain the exact same identifier, count, and order as the source text.
   - Preserve all numerical figures, clinical measurements, SI units, publisher figure/table numbering (e.g., `Hình 1.1`), citations, and web URLs unchanged.

3. **Checkpoint Resilience for Long Texts**:
   - For long medical documents or textbooks, always utilize `scripts/translate_book.py` with SQLite checkpointing (`--output-dir`) to guarantee fault tolerance and token efficiency across interruptions.

4. **Medical Accuracy & Faithfulness**:
   - Do not summarize, shorten, or omit medical content.
   - Do not hallucinate or inject unsolicited clinical recommendations into the author's text.
