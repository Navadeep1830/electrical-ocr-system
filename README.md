# PowerNext Electrical Test Report OCR & Verification System

[![System](https://img.shields.io/badge/System-Air--Gapped%20Local-emerald)](https://github.com)
[![Hardware](https://img.shields.io/badge/GPU-RTX%204050%20%2F%20RTX%202050%20(Local)-blue)](https://github.com)
[![Model](https://img.shields.io/badge/VLM-Qwen2.5--VL--3B--Instruct-purple)](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct)
[![Form](https://img.shields.io/badge/Standard-CPRI%2FQAF%2F01A-orange)](https://cpri.in)

A production-ready, 100% local, air-gapped web application engineered for scanning, extracting, verifying, and storing electrical test request forms—specifically Central Power Research Institute (CPRI) Customer Request Forms like **CPRI/QAF/01A** (Issue No. 02).

Designed specifically for the **PowerNext Hackathon (Track 3 - Automated Test Report Generation System / ATRG)**.

---

## 1. System Architecture & Tech Stack

```
                          ┌───────────────────────────────────────────────┐
                          │   Air-Gapped Local Browser (Vite / React)    │
                          │   Side-by-Side Canvas Inspector & Staging     │
                          └──────────────────────┬────────────────────────┘
                                                 │ HTTP / REST
                                                 ▼
                          ┌───────────────────────────────────────────────┐
                          │          FastAPI Web Service (Port 8000)       │
                          └──────┬───────────────┬────────────────┬───────┘
                                 │               │                │
            ┌────────────────────┘               │                └───────────────────┐
            ▼                                    ▼                                    ▼
┌───────────────────────┐            ┌───────────────────────┐            ┌───────────────────────┐
│ PDF Multi-Page Engine │            │ Local VLM & OCR Engine│            │ SQLite / SQLModel DB  │
│  pypdfium2 @ 300 DPI  │            │  Qwen2.5-VL-3B-Instruct│            │  Audit & Staging      │
│  pdftoppm / PIL       │            │  (torch.float16 CUDA) │            │  FormRecord & Pages   │
└───────────────────────┘            └───────────┬───────────┘            └───────────────────────┘
                                                 │
                                                 ▼
                                     ┌───────────────────────┐
                                     │ Deterministic Regex   │
                                     │ Rating Disaggregator  │
                                     │ (kVA, kV, Ph, Hz, Cu) │
                                     └───────────────────────┘
```

- **Backend:** FastAPI (Python 3.11/3.12) with Uvicorn.
- **Database / ORM:** SQLite with SQLModel (SQLAlchemy 2.0+).
- **PDF & Image Processing:** `pypdfium2` (rendering multi-page PDFs at 300 DPI) and Pillow (PIL).
- **Local VLM Inference:** Hugging Face `transformers` running `Qwen/Qwen2.5-VL-3B-Instruct` in `torch.float16` with `device_map="auto"` (fits inside ~3.2 GB VRAM on NVIDIA RTX 4050/2050 GPUs).
- **Fallback / Dual Engine:** Native Tesseract OCR (`tesseract-ocr`) and heuristic CPRI layout parser ensuring zero-downtime air-gapped operation even during initial model initialization or on CPU hosts.
- **Deterministic Regex Parser:** Custom disaggregation engine extracting Rated Power (kVA/MVA), HV Voltage (kV), LV Voltage (kV), Phase Count, Frequency (Hz), Vector Group (e.g. Dyn11), Cooling Class (ONAN/ONAF), and Conductor Material (Copper/Aluminium).
- **Frontend:** Single-page web application (React 18 + Tailwind CSS via Vite) featuring:
  - Interactive zoomable, pannable document inspector with 300 DPI canvas and forensic high-contrast mode.
  - Side-by-side data staging editor with field-level confidence badges (`High`, `Med`, `Low - Review`).
  - One-click approval, rejection, and JSON/CSV audit export.

---

## 2. Repository File Structure

```text
electrical-ocr-system/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app, CORS, upload & verification endpoints
│   │   ├── config.py            # Model path, upload directories, DB path
│   │   ├── database.py          # SQLModel engine and session dependency
│   │   ├── models.py            # SQLModel database tables (FormRecord, FormPage)
│   │   ├── schemas.py           # Pydantic schemas for VLM extraction & API requests
│   │   ├── parser.py            # Regex normalizer for electrical ratings & checkboxes
│   │   └── vlm_service.py       # Local Qwen2.5-VL-3B inference & prompt templates
│   ├── requirements.txt         # Python package dependencies
│   └── run.py                   # Server launcher script
├── frontend/
│   ├── index.html               # Web application HTML entry point
│   ├── src/
│   │   ├── App.jsx              # Main layout: Top bar, split inspector, KPI dashboard
│   │   ├── components/
│   │   │   ├── DocumentViewer.jsx # Zoomable PDF/Image preview with canvas & forensic contrast
│   │   │   ├── FormEditor.jsx     # Side-by-side field editor with confidence badges
│   │   │   └── RecordTable.jsx    # Table of verified vs pending database entries
│   │   ├── api.js               # Axios / fetch client calls
│   │   ├── main.jsx             # React DOM mount point
│   │   └── index.css            # Tailwind CSS directives
│   ├── package.json             # NPM dependencies
│   ├── vite.config.js           # Vite configuration with API proxy
│   ├── tailwind.config.js       # Tailwind CSS theme settings
│   └── postcss.config.js        # PostCSS configuration
└── README.md
```

---

## 3. Quick Start & Execution

### Prerequisites
- Python 3.11+ (or Python 3.12)
- Node.js 18+ and npm
- NVIDIA GPU with CUDA support (RTX 4050 6GB / RTX 2050 4GB) or CPU mode
- Local Tesseract OCR (`pacman -S tesseract poppler` or `apt-get install tesseract-ocr poppler-utils`)

### Step 1: Backend Setup
```bash
cd /home/navadeep/electrical-ocr-system

# Create virtual environment (using uv or standard python)
uv venv .venv --python 3.12
source .venv/bin/activate

# Install dependencies
uv pip install -r backend/requirements.txt
```

### Step 2: Launch the System
```bash
# Start backend server
source .venv/bin/activate
python backend/run.py
```
The FastAPI backend will start at `http://127.0.0.1:8000` and automatically serve the built frontend application.

### Step 3: Run Frontend in Development Mode (Optional)
If you wish to run the Vite dev server with hot reload:
```bash
cd /home/navadeep/electrical-ocr-system/frontend
npm run dev
```
The Vite development server runs at `http://localhost:5173` and automatically proxies `/api` and `/uploads` to `http://127.0.0.1:8000`.

---

## 4. Extracting the PowerNext Track 3 Form

To extract the specific hackathon file `/home/navadeep/Downloads/Track 3 - AT RG/Customer request form.pdf`:

### Method A: Via Web UI
1. Open `http://localhost:5173` or `http://127.0.0.1:8000` in your browser.
2. Click the banner **"Scan Target Document"** or click **"Scan Local File"**.
3. Confirm the file path `/home/navadeep/Downloads/Track 3 - AT RG/Customer request form.pdf`.
4. Click **"Scan & Ingest"**.
5. The document will be rendered at 300 DPI, extracted, and opened directly in the **Side-by-Side Document Inspector**.

### Method B: Via Direct API Call (curl / CLI)
```bash
curl -X POST http://127.0.0.1:8000/api/process-existing \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/home/navadeep/Downloads/Track 3 - AT RG/Customer request form.pdf"}'
```

### Method C: Batch Folder Scan
```bash
curl -X POST "http://127.0.0.1:8000/api/batch-scan?folder_path=/home/navadeep/Downloads/Track%203%20-%20AT%20RG"
```

---

## 5. Extracted CPRI/QAF/01A Schema & Fields

| Section | Form Field | Normalized Attribute | Extraction Type |
|---|---|---|---|
| **Header** | Format No | `format_no` | Deterministic Header (`CPRI/QAF/01A`) |
| **Header** | Division / Unit | `division_name` | String (`SHORT CIRCUIT LABORATORY`) |
| **Sheet 1** | Customer Name & Address | `customer_name`, `customer_address` | VLM / OCR Text |
| **Sheet 1** | Sample(s) to be tested | `sample_name` | Equipment Category |
| **Sheet 1** | Rating of the sample(s) | `rating_raw` | Complete Raw Rating String |
| **Sheet 1** | Power Rating | `power_rating_kva` | Deterministic Regex Disaggregation (kVA) |
| **Sheet 1** | Voltage HV & LV | `voltage_hv_kv`, `voltage_lv_kv` | Deterministic Regex Disaggregation (kV) |
| **Sheet 1** | Phase Count | `phase_count` | Regex (e.g. `3`) |
| **Sheet 1** | Frequency | `frequency_hz` | Regex (e.g. `50.0` Hz) |
| **Sheet 1** | Cooling Class | `cooling_type` | Regex (`ONAN`, `ONAF`, `AN`) |
| **Sheet 1** | Vector Group | `vector_group` | Regex (`Dyn11`, `Ynd11`, etc.) |
| **Sheet 1** | Conductor Material | `winding_material` | Regex (`Copper`, `Aluminium`) |
| **Sheet 1** | Description of sample | `sample_description` | VLM / OCR Text |
| **Sheet 1** | Type | `sample_type` | Classification |
| **Sheet 1** | Serial Number(s) | `serial_number` | Forensic Identifier |
| **Sheet 1** | Manufacturer's Details | `manufacturer_details` | VLM / OCR Text |
| **Sheet 1** | Drawing Number(s) | `drawing_number` | VLM / OCR Text |
| **Sheet 1** | Details of test(s) requested | `tests_requested` | e.g. `Type Test, Short Circuit` |
| **Sheet 1** | Evaluation Criteria | `evaluation_criteria` | e.g. `IS 1180 / IEC 60076` |
| **Sheet 1** | Sample disposal | `sample_disposal` | Radio/Checkbox Selection |
| **Sheet 2** | MSME Discount | `msme_discount` | `Applicable` / `Not Applicable` |
| **Sheet 2** | Statement of Conformity | `conformity_required`, `conformity_rule`| Checkbox & Rule (i, ii, iii) |
| **Sheet 3** | Sample physical condition | `physical_condition_sample`| `Suitable for Testing` |
| **Sheet 3** | Lab capability | `lab_capability` | `Yes` / `No` |
| **Sheet 3** | Accepting Test Engineer | `test_engineer_name` | Name / Signatory |
| **Audit** | Verification Status | `status` | `PENDING_VERIFICATION`, `VERIFIED`, `REJECTED` |

---

## 6. Verification & Staging Workflow

1. **Deterministic Pre-processing & Ingestion:**
   Upon uploading a PDF, `pypdfium2` converts every page to a high-density 300 DPI raster image, preserving crisp details of handwritten ink and stamps.
2. **Dual-Engine Extraction:**
   The multi-image prompt is fed to `Qwen2.5-VL-3B-Instruct` (or local OCR fallback) to extract structured key-value pairs with confidence scores.
3. **Regex Normalization:**
   Raw ratings like `"250 kVA 11/.433 kV 3Ph 50Hz ONAN Copper"` are disaggregated deterministically into isolated numeric database columns.
4. **Side-by-Side Interactive Staging:**
   The engineer reviews the 300 DPI sheet on the zoomable canvas (with forensic contrast filter) alongside editable staging fields with color-coded confidence badges (`Green: High`, `Yellow: Medium`, `Red: Low`).
5. **Human Sign-Off & Storage:**
   The reviewing engineer records their signature and notes, marks the form as `VERIFIED`, and commits the record to the immutable SQLite database.
6. **Data Export:**
   Export verified records as structured JSON payloads or standardized CSV audit sheets ready for downstream Automated Test Report generation.

---

## 7. Air-Gapped Compliance Guarantee

- **Zero Cloud APIs:** No OpenAI, Claude, or Google Gemini API calls.
- **Zero Telemetry:** No tracking, analytics, or outbound telemetry packets.
- **Local Persistence:** All uploaded files, rendered pages, and database records reside strictly in the local `backend/data/` and `backend/uploads/` directories.
- **Hardware Optimization:** Operates inside 3.2 GB VRAM on NVIDIA RTX 4050/2050 using `torch.float16` and `device_map="auto"`.
