# AegisTrans Medical Specialty Profiles

AegisTrans provides an extensible, modular architecture for translating complex medical and scientific literature from English to Vietnamese. Each medical specialty is represented by a self-contained profile under `medical-translation/profiles/<profile_name>/`.

---

## 1. Directory Structure

```text
medical-translation/
└── profiles/
    ├── dental/                      # Dentistry, Occlusion, TMD, Craniofacial Anatomy
    │   ├── system_prompt.txt
    │   └── glossary_base.jsonl
    └── general_medicine/            # Internal Medicine, Surgery, Physiology, Pharmacology
        ├── system_prompt.txt
        └── glossary_base.jsonl
```

---

## 2. Anatomy of a Specialty Profile

Every profile contains two core files:

### `system_prompt.txt`
Guides the LLM's translation persona, domain rules, and formatting behavior:
- **Academic Tone:** Professional medical Vietnamese terminology conforming to Vietnamese Ministry of Health guidelines.
- **Dual-Language Terminology Mode:** Keeps the original English terminology in parentheses directly following the Vietnamese term upon introduction:
  $$\text{Vietnamese term (English term)}$$
  *(e.g., `xương hàm dưới (mandible)`, `khớp thái dương hàm (temporomandibular joint – TMJ)`, `nhồi máu cơ tim (myocardial infarction – MI)`).*
- **Structural Integrity:** Preserves formatting, figure/table numbers (e.g., `Hình 1.1`), citations, units of measurement, and formula placeholders (`<b0></b0>`).

### `glossary_base.jsonl`
A curated seed dictionary in JSON Lines format with standardized cross-references:
```json
{"en": "temporomandibular joint", "vi": "khớp thái dương hàm", "notes": "TMJ"}
{"en": "articular disc", "vi": "đĩa khớp", "notes": ""}
{"en": "masseter muscle", "vi": "cơ cắn", "notes": ""}
```

---

## 3. Currently Available Profiles

| Profile Name | Domain & Scope | Seed Glossary Size |
| :--- | :--- | :--- |
| **`dental`** *(default)* | Dentistry, Orthodontics, Occlusion, Temporomandibular Disorders (TMD), Oral Maxillofacial Surgery | 100+ terms |
| **`general_medicine`** | Internal Medicine, General Surgery, Human Physiology, Pathology, Clinical Pharmacology | 95+ terms |

---

## 4. How to Add a New Medical Specialty

Adding a new medical specialty (e.g., `cardiology`, `neurology`, `oncology`, `pediatrics`) is straightforward:

1. **Create the profile folder:**
   ```bash
   mkdir -p medical-translation/profiles/cardiology
   ```

2. **Define `system_prompt.txt`:**
   Copy an existing template (e.g., from `general_medicine/system_prompt.txt`) and customize the domain terminology guidelines, clinical style, and terminology preservation rules.

3. **Provide `glossary_base.jsonl`:**
   Add domain terms as JSON Lines with `"en"` and `"vi"` fields:
   ```json
   {"en": "atrial fibrillation", "vi": "rung nhĩ", "notes": "AF"}
   {"en": "ejection fraction", "vi": "phân suất tống máu", "notes": "EF"}
   {"en": "atherosclerosis", "vi": "xơ vữa động mạch", "notes": ""}
   ```

4. **Translate immediately with the new profile:**
   ```bash
   python scripts/translate_book.py textbook.pdf --output-dir output/cardio --profile cardiology
   ```
   AegisTrans will automatically detect and load `cardiology/system_prompt.txt` and `cardiology/glossary_base.jsonl`.
