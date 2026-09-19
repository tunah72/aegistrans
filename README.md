<p align="center">
  <img src=".github/assets/logo.png" alt="AegisTrans logo" width="160">
</p>

<h1 align="center">AegisTrans</h1>

<p align="center">
  <strong>Translate massive medical textbooks and scientific literature into Vietnamese and 35+ languages<br>with layout preservation, dual-language terminology retention, and fault-tolerant checkpointing.</strong>
</p>

<p align="center">
  <a href="https://github.com/tunah72/aegistrans/releases/latest/download/AegisTrans-macos.zip">
    <img src="https://img.shields.io/badge/DOWNLOAD-macOS_Apple_Silicon-000000?style=for-the-badge&logo=apple&logoColor=white" alt="Download AegisTrans for macOS">
  </a>
</p>

<p align="center">
  <a href="https://github.com/tunah72/aegistrans/releases/latest"><img src="https://img.shields.io/github/v/release/tunah72/aegistrans?style=flat-square&label=release" alt="Latest Release"></a>
  <a href="https://github.com/tunah72/aegistrans/releases"><img src="https://img.shields.io/github/downloads/tunah72/aegistrans/total?style=flat-square&label=downloads" alt="Total Downloads"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/tunah72/aegistrans?style=flat-square" alt="AGPL-3.0 License"></a>
  <img src="https://img.shields.io/badge/macOS_App-Apple_Silicon-black?style=flat-square" alt="macOS App">
  <img src="https://img.shields.io/badge/CLI-Cross--Platform-blue?style=flat-square" alt="Cross-Platform CLI">
</p>

<p align="center">
  <a href="#sample-translation-demo">Demo</a> ·
  <a href="#key-features">Features</a> ·
  <a href="#quick-start-desktop-app-macos">Desktop App</a> ·
  <a href="#medical-textbook-translation-cli">Medical Translation</a> ·
  <a href="#build-from-source">Build</a> ·
  <a href="#lineage--acknowledgements">Acknowledgements</a> ·
  <a href="#license--non-commercial-disclaimer">License</a>
</p>

---

## Sample Translation Demo

Side-by-side comparison from a real medical pilot translation (*Okeson – Management of Temporomandibular Disorders and Occlusion*, Elsevier 8th Edition):

<div align="center">
  <table>
    <thead>
      <tr>
        <th width="50%" align="center"><strong>Original English Source</strong></th>
        <th width="50%" align="center"><strong>Vietnamese (Bilingual Terminology Mode)</strong></th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td valign="top"><img src=".github/assets/page_1_src.png" alt="Original English PDF Page 1" width="100%"/></td>
        <td valign="top"><img src=".github/assets/page_1_bilingual_v2.png" alt="Vietnamese Translated PDF Page 1" width="100%"/></td>
      </tr>
    </tbody>
  </table>
</div>

> [!TIP]
> **Key Highlights:**
> - **Typography & Layout Preservation:** Retains publisher banner headers, section titles, column geometries, figures, and crisp typography without text clipping or irregular overflows.
> - **Dual-Language Terminology Retention:** Clinical concepts are translated into standard Vietnamese accompanied by the original English term in parentheses (e.g., `xương hàm dưới (mandible)`, `khớp thái dương hàm (temporomandibular joint – TMJ)`, `dây chằng nha chu (periodontal ligament)`). Readers gain immediate contextual understanding while simultaneously mastering international academic terminology.

---

## Key Features

- **Native macOS Desktop App:** One-click pre-packaged standalone application (`AegisTrans.app` for Apple Silicon). Comes pre-bundled with the ONNX layout model and font assets — no Python runtime or command-line setup required.
- **Cross-Platform CLI Suite:** Fully supported on macOS, Linux, and Windows via Python CLI for automated batch pipelines and server deployments.
- **Strict Layout Preservation:** Preserves multi-column flow, mathematical formulas, chemical equations, figures, captions, tables, and document bookmarks.
- **Academic & Medical Textbook Pipeline:**
  - **Bilingual Terminology Learning Mode:** Dynamically injects English terms alongside standardized Vietnamese nomenclature.
  - **Modular Specialty Profiles:** Extensible profile registry under `medical-translation/profiles/` (includes Dentistry/TMD `dental` and General Medicine `general_medicine`).
  - **Chapter Chunking & Bookmark-Preserving TOC Merging:** Slices massive textbooks into chapter PDFs using bookmark trees and re-merges translated chapters with navigational bookmarks intact.
  - **Fault-Tolerant SQLite Checkpointing:** Caches sentence-level translations into SQLite. Resumes seamlessly after connection interruptions without re-translating or wasting LLM tokens.
- **Multiple Translation Engines:**
  - Zero-config free mode via Google Translate web service for fast drafts.
  - Advanced LLM gateways (OpenAI GPT-4o, Google Gemini 2.5/3.8 Flash, Anthropic Claude, Ollama, 9router) for nuanced academic accuracy.

---

## Quick Start (Desktop App - macOS)

1. **[Download AegisTrans-macos.zip](https://github.com/tunah72/aegistrans/releases/latest/download/AegisTrans-macos.zip)** (~200 MB).
2. Extract the archive and drag `AegisTrans.app` to your `/Applications` folder.
3. Launch `AegisTrans`.

> [!NOTE]
> **macOS Gatekeeper Notice:**  
> Because AegisTrans is an independent community project without an expensive Apple Developer ID signature, macOS may display an *"unidentified developer"* or *"app is damaged"* notification on first launch.  
> - **Option A:** Right-click (or Control-click) `AegisTrans.app` $\rightarrow$ Select **Open** $\rightarrow$ Click **Open**.  
> - **Option B:** Open Terminal and execute:
>   ```bash
>   xattr -cr /Applications/AegisTrans.app
>   ```

### Running on Windows & Linux
To ensure product integrity and honest open-source practices, binary desktop packages are currently released and verified exclusively for macOS (the maintainer's primary hardware environment). Users on Windows and Linux can execute AegisTrans directly using the Python CLI or run the GUI via:
```bash
python -m app.gui
```

---

## Medical Textbook Translation (CLI)

For large textbooks (200–800+ pages), use the dedicated orchestrator suite:

### 1. Configure Gateway / API Credentials
Create a `.env` file at the repository root (see `.env.example`):
```env
OPENAI_BASE_URL=http://localhost:20128/v1
OPENAI_API_KEY=your_api_key_or_gateway_token
LLM_MODEL=ag/gemini-3.8-flash-low
```

### 2. Translate a Book with Checkpoint Resume
```bash
python scripts/translate_book.py path/to/textbook.pdf \
    --output-dir output/my_book \
    --profile dental \
    --concurrency 2
```
*Available profiles:* `--profile dental` (Dentistry & TMD) or `--profile general_medicine` (Internal Medicine, Surgery, Pharmacology).

### 3. Full Textbook Workflow (Split $\rightarrow$ Batch Translate $\rightarrow$ Merge TOC)
```bash
# Step 1: Split book into chapter PDFs based on PDF bookmarks
python scripts/split_pdf_by_chapters.py books/textbook.pdf --output-dir books/chapters

# Step 2: Batch translate all chapters and merge into final book
python scripts/translate_all_chapters.py \
    --chapters-dir books/chapters \
    --output-dir output/chapters \
    --final-pdf output/Textbook_Vietnamese.pdf \
    --profile dental \
    --concurrency 2
```

---

## Build from Source

```bash
# Clone repository
git clone https://github.com/tunah72/aegistrans.git
cd aegistrans

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements-app.txt

# Run automated tests
python -m unittest discover tests

# Build native macOS desktop application (.app and .zip)
./build.sh
```

---

## Lineage & Acknowledgements

AegisTrans stands on the shoulders of giants in the open-source document processing ecosystem:

- **[PDFMathTranslate-next](https://github.com/PDFMathTranslate/PDFMathTranslate-next):** The overarching concept and architectural inspiration originated when discovering this work through Chip Huyen's curated *GoodAIList*.
- **[VI-Translate](https://github.com/breslee1707/VI-Translate):** Authored by `breslee1707`. Provided the initial Vietnamese localization foundation and desktop UI concepts discovered via Facebook developer communities.
- **[BabelDOC](https://github.com/funstory-ai/BabelDOC):** Powers layout detection via ONNX and font typography assets.
- **Our Specialized Contribution:** While predecessors focused on general mathematical and scientific documents, AegisTrans is purpose-built for **exhaustive Medical & Dental Textbooks**. It introduces dual-language terminology retention, specialized domain prompts, PDF chapter slicing, bookmark-preserving TOC reconstruction, and SQLite-backed interrupted translation resumption.

---

## License & Non-Commercial Disclaimer

This project is licensed under the **[GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE)**.

> [!IMPORTANT]
> **Community & Non-Commercial Purpose:**  
> AegisTrans is an independent, non-commercial open-source project created to assist healthcare students, medical practitioners, dentists, and academic researchers in studying international literature. It is distributed free of charge with zero commercial intent.
> 
> **Notice & Takedown Policy:**  
> We strictly respect intellectual property rights. If you are a copyright owner, publisher, or author and believe any sample text, graphic, or code snippet in this repository infringes your rights or requires updated attribution, please reach out directly:
> - **Maintainer:** [@tunah72](https://github.com/tunah72)
> - **Issue Tracker:** [GitHub Issues](https://github.com/tunah72/aegistrans/issues)
> 
> All inquiries will be addressed promptly, and requested items will be modified or removed immediately.
