# ExcelLence AI — Project Overview, Tech Stack & App Flow

> An AI-powered spreadsheet intelligence platform that turns unstructured content
> (text prompts, images, PDFs, and web pages) into clean, structured, Excel-ready tables.
>
> This document describes what is **actually implemented in the codebase today** (Phase 1 —
> *Intelligent Data Extraction*) and maps it against the broader product vision. Where the
> docs describe planned work, it is clearly labelled **(Planned)**.

---

## 1. What the App Does Today

ExcelLence AI (codename **ExcelAI**) is currently a **Phase 1 data-extraction app**. A signed-in
user provides data in one of three ways and the app returns a structured, editable, exportable table:

| Input mode | What the user gives | What happens |
|------------|--------------------|--------------|
| **Text Prompt** | A request or raw text (e.g. *"Top 10 EV companies by market cap 2024"*) | The LLM generates / extracts a structured table |
| **Image / PDF Upload** | PNG, JPG, WEBP, or PDF | OCR extracts text → topics detected → LLM structures the chosen table(s) |
| **URL Input** | A web page URL | Page is scraped for HTML tables → topics detected → LLM structures the chosen table(s) |

Every result can be **previewed, sorted, inline-edited, enriched with calculated columns**, and
**exported to Excel (.xlsx), CSV, or PDF**.

---

## 2. Tech Stack

### 2.1 Backend — Python / FastAPI

| Concern | Technology | Notes |
|---------|-----------|-------|
| Web framework | **FastAPI** | ASGI app in `backend/main.py`; also serves the static frontend |
| ASGI server | **Uvicorn** | Local dev: `uvicorn backend.main:app --reload` |
| AI / LLM | **Groq SDK** (`groq`) | Model: `llama-3.3-70b-versatile` (configurable via `GROQ_MODEL`) |
| OCR (images) | **pytesseract** + **Pillow** | Wraps the Tesseract engine |
| PDF text | **pypdf** | Native text extraction from digital PDFs |
| Scanned PDF OCR | **PyMuPDF** (`fitz`) + pytesseract | Renders pages to images, then OCRs them (fallback) |
| Web scraping | **httpx** (async) + **BeautifulSoup4** | Fetches page, parses up to 5 `<table>` elements |
| Excel export | **openpyxl** | Styled workbook with header fills, table styles, auto-width |
| PDF export | **reportlab** | Branded landscape/portrait table document |
| Auth | **python-jose** (JWT) + **bcrypt** | HS256 tokens, bcrypt-hashed passwords |
| Validation | **Pydantic** (+ `email-validator`) | Request/response schemas in `backend/models/schemas.py` |
| Config | **python-dotenv** | Loads `backend/.env` in development |
| File uploads | **python-multipart** | Multipart form handling for image/PDF uploads |

> ⚠️ **Dependency note:** the project-root `requirements.txt` (used for deployment) is missing
> `pypdf`, `pymupdf`, and `reportlab`, which the code imports. The complete list lives in
> `backend/requirements.txt`. PDF OCR / PDF export will fail at runtime unless those are installed.

### 2.2 Frontend — Vanilla Web (no framework)

| Concern | Technology | Notes |
|---------|-----------|-------|
| Markup | Plain **HTML** | `frontend/index.html` (login), `frontend/app.html` (workspace) |
| Styling | Plain **CSS** | `css/login.css`, `css/app.css`; "dark-luxury" theme, Google Fonts (Nunito / Inter / JetBrains Mono) |
| Logic | **Vanilla JavaScript** (IIFE modules) | No build step, no bundler; everything hangs off a global `window.ExcelAI` namespace |
| State | In-memory JS object + `localStorage` | JWT stored in `localStorage` under `excelai_token` |

Frontend JS modules:

- **`js/api.js`** — fetch wrapper, JWT decode/validation, file download helper, toast notifications (exposes `window.ExcelAI`)
- **`js/auth.js`** — login/signup form handling (login page only)
- **`js/app.js`** — main workspace controller: modes, extraction orchestration, exports, toolbar actions
- **`js/table.js`** — table rendering, sorting, inline editing, raw-JSON view, column statistics
- **`js/toolbar.js`** — ribbon-style toolbar rendering (Excel-like Home/Insert/View/Export tabs)

### 2.3 Infrastructure & Deployment

| Concern | Technology |
|---------|-----------|
| Hosting | **Vercel** (`@vercel/python`, runtime `python3.11`, `maxLambdaSize: 50mb`) |
| Routing | `vercel.json` routes **all** requests to `backend/main.py` (FastAPI serves both API and static files) |
| Persistence | **None** — no database. Users live in an in-memory dict; extracted data lives only in the browser |

### 2.4 Architecture Summary

```
Monolithic FastAPI service
├── Serves the static frontend (HTML/CSS/JS)
├── Exposes a JSON REST API under /api/*
└── Calls out to: Groq (LLM), Tesseract (OCR), and arbitrary URLs (scraping)

Single deployable unit → Vercel serverless (Python).
No database; stateless between requests except client-held JWT + table data.
```

---

## 3. Project Structure

```
excelai/
├── vercel.json                 # Vercel build/route config (all → backend/main.py)
├── requirements.txt            # Deployment deps (NOTE: incomplete — see §2.1)
├── README.md                   # Run instructions, env vars, API list
│
├── backend/
│   ├── main.py                 # FastAPI app: CORS, routers, static mounts, SPA catch-all
│   ├── .env.example            # Required environment variables
│   ├── requirements.txt        # Full backend dependency list
│   ├── routes/
│   │   ├── auth.py             # /api/auth/* — JWT login/signup/me (in-memory users)
│   │   ├── extract.py         # /api/extract/* — text/image/url/ocr/topics
│   │   ├── export.py          # /api/export/excel, /api/export/csv
│   │   └── export_pdf.py      # /api/export/pdf (reportlab)
│   ├── services/
│   │   ├── groq_service.py    # LLM table generation (4-tier retry + fallback), calc columns
│   │   ├── ocr_service.py     # Image OCR + PDF text/scanned-PDF OCR
│   │   ├── scraper_service.py # httpx + BeautifulSoup web scraping
│   │   └── excel_service.py   # openpyxl workbook builder + styling
│   ├── models/
│   │   └── schemas.py         # Pydantic request/response models
│   └── utils/
│       └── helpers.py         # Fallback parser, type inference, JSON/CSV helpers
│
└── frontend/
    ├── index.html              # Login / signup page
    ├── app.html                # Main workspace (chat panel + table panel)
    ├── assets/logo.svg
    ├── css/   (login.css, app.css)
    └── js/    (api.js, auth.js, app.js, table.js, toolbar.js)
```

---

## 4. API Reference (Implemented)

All `/api/extract/*` and `/api/export/*` endpoints require a **Bearer JWT** (`Authorization: Bearer <token>`).

### Auth — `/api/auth`
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/login` | Validate credentials, return JWT + user |
| POST | `/signup` | Create in-memory user, return JWT |
| GET | `/me` | Return current user from JWT |

### Extraction — `/api/extract`
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/text` | Generate/extract a table from a text prompt (+ optional calculated columns) |
| POST | `/image` | OCR an uploaded image/PDF, then structure it into a table |
| POST | `/url` | Scrape a URL and structure the primary table |
| POST | `/ocr` | OCR-only: return raw text for an upload (no LLM) |
| POST | `/detect-topics` | Pre-scan a URL/image for candidate tables (sub-tables) |
| POST | `/selected-topics` | Run extraction only on user-selected tables (+ calc columns, chunked for big inputs) |

### Export — `/api/export`
| Method | Path | Output |
|--------|------|--------|
| POST | `/excel` | `.xlsx` (openpyxl, styled) |
| POST | `/csv` | `.csv` (UTF-8) |
| POST | `/pdf` | `.pdf` (reportlab, branded) |

### Misc
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness check |
| GET | `/`, `/{path}` | Serve the frontend (SPA-style catch-all) |

---

## 5. How the App Works (End-to-End Flow)

### 5.1 High-Level Lifecycle

```
┌──────────┐   login    ┌───────────────┐   pick input    ┌──────────────────┐
│  Browser │──────────▶ │  JWT issued   │───────────────▶ │   Workspace UI    │
│ (login)  │            │ (localStorage)│                 │ text/image/url    │
└──────────┘            └───────────────┘                 └────────┬─────────┘
                                                                   │ extract
                                                                   ▼
                                          ┌────────────────────────────────────┐
                                          │  FastAPI /api/extract/*  (JWT-auth) │
                                          │  OCR → Scrape → Groq LLM → JSON     │
                                          │  (fallback parser if LLM fails)     │
                                          └───────────────┬────────────────────┘
                                                          │ {columns, rows, confidence, warnings}
                                                          ▼
                                          ┌────────────────────────────────────┐
                                          │  Table preview (sort/edit/stats)    │
                                          │  + calculated columns               │
                                          └───────────────┬────────────────────┘
                                                          │ export
                                                          ▼
                                          ┌────────────────────────────────────┐
                                          │  /api/export/{excel|csv|pdf}        │
                                          │  → file download                    │
                                          └────────────────────────────────────┘
```

### 5.2 Authentication Flow
1. User opens `index.html`. If a **valid JWT** already exists in `localStorage`, they are redirected straight to `app.html`.
2. On login/signup, `auth.js` POSTs to `/api/auth/login` or `/api/auth/signup`.
3. `auth.py` checks the bcrypt password hash against the **in-memory `_DEMO_USERS` dict** and issues an HS256 JWT (`sub = email`, configurable expiry, default 1 day).
4. The token is stored in `localStorage` (`excelai_token`) and sent as a Bearer header on every API call.
5. `app.js` guards the workspace: no/expired token → redirect back to login. It also calls `/api/auth/me` to load the user profile for the toolbar.

> **Important:** Users and passwords are **not persisted**. Restarting/redeploying the backend
> resets everyone to the two seeded demo accounts. There is no real database yet.

**Demo accounts:** `demo@excelai.dev / ExcelAI123!` and `admin@excelai.dev / AdminExcelAI123!`

### 5.3 Text Extraction Flow
```
User types prompt ─▶ app.js POST /api/extract/text {prompt, calculated_columns}
                       └▶ groq_service.generate_table("TEXT", prompt)
                            ├─ Build system+user prompt (strict JSON contract)
                            ├─ Try Groq (4 escalating attempts, see §5.7)
                            ├─ If all fail → helpers.build_fallback_table()
                            └─ helpers.apply_calculated_columns() (BODMAS via safe AST)
                       ◀─ {columns, rows, confidence, warnings, table_title}
                     app.js renders the table + confirmation bar
```

### 5.4 Image / PDF Extraction Flow
```
User uploads file ─▶ app.js POST /api/extract/ocr (multipart)
                       └▶ ocr_service.extract_text_from_upload()
                            ├─ PDF? → pypdf text; if empty → PyMuPDF render + pytesseract
                            └─ Image? → Pillow → pytesseract
                       ◀─ {text, metadata}
                     POST /api/extract/detect-topics {content_type:"image", content:text}
                       ◀─ topics + sub-tables (row estimates)
                     UI shows a checkbox selector → user picks tables
                     POST /api/extract/selected-topics {content, selected_ids, calc cols}
                       └▶ groq_service (chunked if content > 20k chars)
                       ◀─ structured table
```
> If no topics are detected, the UI falls back to a direct `POST /api/extract/image`
> (OCR + LLM in one step). Image cells that look like OCR misreads (e.g. `S`↔`5`, `l`↔`1`)
> are visually flagged as low-confidence in the table.

### 5.5 URL Extraction Flow
```
User enters URL ─▶ app.js POST /api/extract/detect-topics {content_type:"url", content:url}
                     └▶ scraper_service.scrape_url()
                          ├─ httpx GET (browser User-Agent, follows redirects)
                          ├─ BeautifulSoup → up to 5 <table>s (max 100 rows each)
                          └─ Title + tables + first 40k chars of body text
                     ◀─ topics (per-table row estimates) + scraped_content
                   UI shows selector → user picks tables
                   POST /api/extract/selected-topics {content:scraped, selected_ids, calc cols}
                     ◀─ structured table
```
> Fallback path: if topic detection yields nothing, the UI calls `POST /api/extract/url`
> directly, passing an optional "which table?" clarification to guide the LLM.

### 5.6 Preview → Edit → Export Flow
1. The response (`columns`, `rows`, `confidence`, `warnings`, `table_title`) is stored in client state and rendered by `table.js`.
2. The user can **sort** columns (numeric-aware), toggle **Edit Mode** (inline `contentEditable` cells), view **Raw JSON**, or open **Column Stats** (min/max/avg/count per numeric column).
3. **Calculated columns**: the user defines `name` + `formula` using `col_0`, `col_1`, … references. The server evaluates them safely with an AST walker that only permits `+ - * /` and unary signs (no function calls, no subscripts).
4. On export, `app.js` POSTs the current columns/rows to `/api/export/{excel|csv|pdf}`; the backend streams back a file which the browser downloads.

### 5.7 LLM Extraction Resilience (groq_service)
The extraction engine is built to **always return a usable table**:

1. **Attempt 1** — strict JSON mode, full prompt.
2. **Attempt 2** — relaxed JSON mode with an explicit "MUST return valid JSON" reminder.
3. **Attempt 3** — simplified system prompt on the first 3,000 chars of content.
4. **Attempt 4** — "identify structure first, then extract" prompt on the first 2,000 chars.
5. **Fallback** — `helpers.build_fallback_table()` parses the raw text heuristically
   (delimiter detection, key:value pairs, type inference) and attaches a warning.

Large inputs (>20k chars) are split line-wise into chunks and merged
(`extract_large_dataset`). Long content is truncated to ~50k chars while preserving headers.
Column types (`number`, `currency`, `date`, `percentage`, `text`) are inferred and used to
format Excel cells.

---

## 6. Environment & Running Locally

Required environment variables (`backend/.env`, copied from `.env.example`):

| Variable | Purpose | Default |
|----------|---------|---------|
| `GROQ_API_KEY` | Groq API key (from console.groq.com) | — (required for LLM; fallback used if missing) |
| `SECRET_KEY` | JWT signing secret (≥32 chars) | `excelai-dev-secret` |
| `ALGORITHM` | JWT algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token lifetime | `1440` (1 day) |
| `CORS_ORIGINS` | Allowed frontend origins (comma-sep, `*` = all) | `*` |
| `GROQ_MODEL` | Groq model name | `llama-3.3-70b-versatile` |

```bash
# Backend
cd excelai
python -m uvicorn backend.main:app --reload

# Frontend
# Served automatically by FastAPI at http://localhost:8000/
# (or open frontend/index.html via any static dev server)
```

External runtime requirement: **Tesseract OCR** must be installed on the host for image/scanned-PDF OCR.

---

## 7. Roadmap — Current Code vs. Product Vision

The long-term vision is to evolve from a data-extraction tool into a full **AI-native spreadsheet
operating system**. Status against the documented phases:

| Phase | Capability | Status in codebase |
|-------|-----------|--------------------|
| **1. Intelligent Data Extraction** | Text/image/PDF/URL extraction, OCR, preview/validation, Excel/CSV/PDF export | ✅ **Implemented** |
| **2. AI Spreadsheet Workspace** | Upload workbooks, multi-sheet editing, AI copilot, formula generation, data cleaning/transformation | 🚧 **Planned** (limited inline editing + calculated columns exist) |
| **3. Analytics & Insights** | Auto charts, KPI dashboards, summaries, trend/anomaly detection, BI reports | 🚧 **Planned** (only basic column stats today) |
| **4. AI Agents & Automation** | Research / Extraction / Analytics / Report / Workflow agents | 🚧 **Planned** |
| **5. Enterprise Platform** | Team workspaces, collaboration, version control, RBAC, API integrations, cloud, security | 🚧 **Planned** |

**Vision:** *Transform raw information into business intelligence through simple conversations with AI* —
targeting Finance, Accounting, Operations, Research, BI, Education, Consulting, and Data Analytics.

---

## 8. Known Gaps & Considerations

- **No database / persistence** — users and extracted data are ephemeral. A real datastore (and migration off the in-memory user dict) is needed before multi-user or enterprise use.
- **Deployment dependency drift** — root `requirements.txt` omits `pypdf`, `pymupdf`, `reportlab`; align it with `backend/requirements.txt` to avoid runtime import errors on Vercel.
- **OCR host dependency** — Tesseract must be present in the deployment image; the default Vercel Python runtime does not include it.
- **CORS** — defaults to `*`; lock down `CORS_ORIGINS` to the real domain in production.
- **Secret defaults** — `SECRET_KEY` falls back to a known dev value; must be overridden in production.
- **No automated tests** — there is no test suite in the repository yet.

---

*Generated as living documentation of the ExcelLence AI (ExcelAI) codebase. Update alongside the source as phases land.*
