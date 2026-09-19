# Contributing to AegisTrans

Thank you for your interest in contributing to **AegisTrans**! 

AegisTrans is an open-source initiative dedicated to translating massive medical textbooks and scientific literature into Vietnamese (and other Latin-script languages) while preserving complex multi-column typography, formulas, figures, tables, and bookmarks. It features an integrated dual-language terminology retention mode `Vietnamese term (English term)` and fault-tolerant SQLite checkpoint resumption.

---

## 1. Lineage, Ethics & Takedown Policy

AegisTrans is built upon and inspired by pioneering open-source projects:
- **[PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next):** Conceptual inspiration discovered through Chip Huyen's curated *GoodAIList*.
- **[VI-Translate](https://github.com/breslee1707/VI-Translate):** Authored by `breslee1707`, which provided foundational Vietnamese localization and desktop GUI concepts.
- **Non-Commercial Educational Mission:** This project is developed by [@tunah72](https://github.com/tunah72) strictly for educational, academic, and clinical learning purposes. It is distributed free of charge under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
- **Notice & Takedown Policy:** We respect the intellectual property rights of all authors and publishers. If you are a copyright owner and believe any sample text, asset, or reference in this repository infringes upon your rights, please open an Issue or contact the maintainer directly. Any identified items will be reviewed and removed or updated immediately.

---

## 2. Development Setup

### System Prerequisites
- **Python**: 3.10 – 3.12 (Python 3.12 recommended).
- **Operating System**: macOS (Apple Silicon / Intel) for desktop packaging; Linux, macOS, or Windows for core engine, CLI, and profile development.

### Installation
```bash
# 1. Clone the repository
git clone https://github.com/tunah72/aegistrans.git
cd aegistrans

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .\.venv\Scripts\Activate.ps1

# 3. Install core, GUI, and packaging dependencies
pip install -r requirements-app.txt

# 4. (Optional) Set up LLM API credentials for medical translation
cp .env.example .env
# Edit .env with your OpenAI-compatible API base URL and token
```

---

## 3. Automated Testing

Before opening a pull request or committing changes, ensure that all automated tests pass:

```bash
python -m unittest discover tests
```

### Test Suite Overview
- `tests/test_profiles.py`: Validates discovery, asset loading, and syntax of medical specialty profiles.
- `tests/test_checkpoint.py`: Tests SQLite-backed interrupted translation storage and resumption.
- `tests/test_glossary.py`: Tests terminology lookup, persistence, and prompt injection.
- `tests/test_openai_translator.py`: Tests LLM translation gateways and network resilience.
- `tests/test_validation.py`: Tests formula placeholder `<b0></b0>` integrity enforcement.
- `tests/test_app_gui.py`: Tests desktop UI event dispatching and helper routines.
- `tests/test_preservation_rules.py`: Tests font, layout, and document structure preservation rules.

---

## 4. Codebase Architecture

```text
AegisTrans/
├── plugin.json                  # Antigravity plugin manifest
├── SKILL.md                     # Agent skill runbook and instructions
├── rules/
│   └── AGENTS.md                # Agent translation guidelines and terminology constraints
├── medical-translation/
│   ├── README.md                # Medical profiles architecture documentation
│   └── profiles/
│       ├── dental/              # Dentistry, TMD, Occlusion, Craniofacial Anatomy
│       └── general_medicine/    # Internal Medicine, Surgery, Physiology, Pharmacology
├── pdf2zh/                      # Core translation engine
│   ├── profiles.py              # Profile discovery, loading, and validation
│   ├── checkpoint.py            # SQLite state management
│   ├── glossary.py              # Terminology glossary manager
│   ├── doclayout.py             # ONNX page layout analysis
│   ├── pdfinterp.py             # PDF text extraction and typography mapping
│   ├── converter.py             # PDF rebuild and font rendering
│   └── translator.py            # Translation engine interfaces
├── scripts/
│   ├── translate_book.py        # Single textbook translation with checkpoint resume
│   ├── split_pdf_by_chapters.py # Splits books by PDF bookmark outlines
│   ├── translate_all_chapters.py# Batch chapter translator with TOC-preserving merger
│   └── translate_pdf.py         # Single-document CLI runner
└── app/                         # Desktop GUI application (Tkinter / PyInstaller)
```

---

## 5. Contributing a New Medical Specialty Profile

AegisTrans uses an extensible profile registry under `medical-translation/profiles/<specialty>/`.

To contribute a new specialty (e.g., `cardiology`, `pediatrics`, `neurology`):

1. **Create the profile directory:**
   ```bash
   mkdir -p medical-translation/profiles/cardiology
   ```
2. **Author `system_prompt.txt`:**
   Define clinical translation standards, domain terminology rules, and ensure the prompt enforces dual-language retention:
   $$\text{Vietnamese term (English term)}$$
3. **Curate `glossary_base.jsonl`:**
   Add validated seed terminology pairs in JSON Lines format:
   ```json
   {"en": "myocardial infarction", "vi": "nhồi máu cơ tim", "notes": "MI"}
   {"en": "atrial fibrillation", "vi": "rung nhĩ", "notes": "AF"}
   ```
4. **Validate the profile:**
   Run the automated test suite to confirm your profile passes structure and JSON syntax verification:
   ```bash
   python -m unittest tests/test_profiles.py
   ```

---

## 6. Packaging Desktop Releases (macOS)

Desktop releases are built natively on macOS via `./build.sh`:

```bash
# Build standalone AegisTrans.app and package AegisTrans-macos.zip
./build.sh

# Fast build (skipping ONNX model and font downloads if already cached)
./build.sh --skip-assets

# Clean previous build artifacts
./build.sh --clean
```

> **Platform Transparency Note:**  
> Because the maintainer's primary workstation is macOS, standalone `.app` bundles are built and verified exclusively for macOS. Linux and Windows users are encouraged to run AegisTrans directly via Python CLI (`python scripts/translate_book.py`) or launch the GUI via `python -m app.gui`.

---

## 7. Versioning & Release Process

1. Increment `APP_VERSION` in `app/update.py` following [Semantic Versioning](https://semver.org):
   ```python
   APP_VERSION = "0.2.2"
   ```
2. Update `README.md` or changelog notes as necessary.
3. Commit the version bump and create an annotated git tag:
   ```bash
   git tag v0.2.2
   ```
4. The `.github/workflows/release.yml` GitHub Actions pipeline will automatically:
   - Validate tag consistency against `app/update.py`.
   - Build `AegisTrans.app` on `macos-latest`.
   - Compress the application into `dist/AegisTrans-macos.zip`.
   - Publish a new GitHub Release with the bundled archive.

---

## 8. Maintainer Contact

For technical questions, suggestions, or takedown notices, please open a GitHub Issue or reach out to:
- **Maintainer:** [@tunah72](https://github.com/tunah72)
- **Repository:** [https://github.com/tunah72/aegistrans](https://github.com/tunah72/aegistrans)
