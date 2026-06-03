# ExcelLence AI — "Excel Skills" Integration Plan

> Goal: give ExcelLence the ability to turn **data, web pages, and images** into
> **polished, presentable, multi-sheet Excel workbooks** with charts, formulas, KPIs,
> formatting, and written analysis — the kind of output people associate with
> "Claude making spreadsheets" — while staying **Groq-only and cost-friendly**.

## Decisions (locked)

| Fork | Decision | Why |
|------|----------|-----|
| **Excel engine** | **Spec → openpyxl renderer** | Safe (no code execution), deterministic, testable, zero new dependencies, runs anywhere |
| **LLM** | **Groq only** (`llama-3.3-70b-versatile`) for extraction *and* design | Single provider, lowest cost |
| **Hosting** | **Move API to a container** (Render/Railway/Fly) | Unlocks Tesseract OCR, long timeouts, persistent storage, a real DB |

---

## 1. The core idea — how the "skill" actually works

A real "Excel skill" is two things: **(a) knowledge of how to design a good spreadsheet**, and
**(b) a reliable way to produce the file**. We split those cleanly:

```
                    ┌──────────────────────────────────────────────┐
   extracted data   │  Groq = THE DESIGNER (small, cheap call)      │
  {columns, rows}   │  Sees: column schema + sample rows + STATS    │
        │           │  Returns: which charts, which KPIs, narrative │
        │           └───────────────────────┬──────────────────────┘
        │                                   │ design (JSON, no data rows)
        ▼                                   ▼
  ┌───────────────┐   inject real rows + computed numbers   ┌─────────────────────┐
  │ Python = MATH │ ──────────────────────────────────────▶ │ WorkbookSpec (JSON)  │
  │ compute_stats │                                          └──────────┬──────────┘
  └───────────────┘                                                     │
                                                                        ▼
                                              ┌────────────────────────────────────┐
                                              │ workbook_builder.py (openpyxl)      │
                                              │ → Dashboard + Data sheets, charts,  │
                                              │   formats, formulas, conditional fmt │
                                              │ → polished .xlsx                     │
                                              └────────────────────────────────────┘
```

### The cost trick (important)
**The LLM never receives or re-types the data rows.** It only sees the column schema, a
~8-row sample, and **pre-computed statistics**. It returns a compact *design*. Python then
injects the full rows and computes every KPI/aggregate. Result:

- Token usage stays tiny and **flat**, even for 10,000-row tables (no truncation risk).
- **No LLM arithmetic** → no hallucinated totals.
- One cheap Groq call per report (a few hundred tokens), with a **deterministic fallback**
  design if Groq is unavailable — so the feature never hard-fails.

---

## 2. What was already built (foundation — committed to the repo)

These files are in place and pass an end-to-end smoke test (Dashboard + Data tabs, 2 charts,
computed KPIs, currency formatting, valid re-openable `.xlsx`):

| File | Role |
|------|------|
| `backend/models/workbook_schemas.py` | The declarative **WorkbookSpec** contract (sheets, charts, KPIs, conditional formats) + the `WorkbookBuildRequest` API model |
| `backend/services/workbook_builder.py` | **Deterministic renderer**: WorkbookSpec → polished `.xlsx` (styled headers, number formats, banded rows, freeze panes, autofilter, charts, conditional formatting, dashboard sheet) |
| `backend/services/workbook_ai.py` | **Groq designer** + `compute_stats` + KPI formatting + guaranteed `_default_design` fallback |
| `backend/routes/workbook.py` | `POST /api/workbook/design` (preview JSON) and `POST /api/workbook/build` (download `.xlsx`) |
| `backend/main.py` | Router registered |

### Try it now (locally)
```bash
cd excelai
# requires: openpyxl, groq, email-validator (already in backend/requirements.txt)
python -m uvicorn backend.main:app --reload
```
`POST /api/workbook/build` with a JWT and a body like:
```json
{
  "columns": [{"name":"Month","type":"text"},{"name":"Revenue","type":"currency"},
              {"name":"Units","type":"number"},{"name":"Growth","type":"percentage"}],
  "rows": [["Jan","12000","320","5%"],["Feb","15500","410","29%"]],
  "intent": "Quarterly sales performance summary",
  "theme": "corporate",
  "filename": "Sales Report"
}
```
→ streams back a polished `Sales Report.xlsx`. Set `GROQ_API_KEY` to get AI-designed
charts/KPIs/narrative; without it you still get a clean fallback report.

---

## 3. Capabilities → how each is delivered

| Capability you asked for | How it's implemented |
|--------------------------|----------------------|
| **Make sheets** | `WorkbookSpec.sheets[]` → one styled data sheet (extensible to many) + a `Dashboard` sheet |
| **Graphs / charts** | `ChartSpec` → openpyxl `BarChart` / `LineChart` / `PieChart` / `AreaChart`, auto-chosen by Groq (bar=compare, line=trend, pie=composition) |
| **Analysis on data** | `compute_stats()` (sum/avg/min/max/count/growth) → KPI cards + Groq narrative insights on the dashboard |
| **URL → Excel** | existing `scraper_service` → extraction → `build_polished_spec` → workbook |
| **Image/PDF → Excel** | existing `ocr_service` (Tesseract on the container) → extraction → workbook |
| **Polished & presentable** | Themed headers, number formats, banded rows, frozen header, autofilter, conditional color scales/data bars, KPI dashboard, written summary |
| **Formulas** | `SheetSpec.formulas` → real Excel formulas written into cells (`=B2*C2`) — also reuses your existing safe calculated-columns feature |

---

## 4. Step-by-step roadmap

### Phase 0 — Move the API to a container *(prerequisite for OCR + heavy jobs)*
1. Add a `Dockerfile` to `excelai/`:
   ```dockerfile
   FROM python:3.11-slim
   RUN apt-get update && apt-get install -y tesseract-ocr && rm -rf /var/lib/apt/lists/*
   WORKDIR /app
   COPY backend/requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```
2. Deploy to **Render / Railway / Fly.io** (point the platform at the Dockerfile).
3. Set env vars (`GROQ_API_KEY`, `SECRET_KEY`, `CORS_ORIGINS`, `GROQ_MODEL`).
4. Keep the **frontend on Vercel** (static) and point its API base at the new backend URL,
   or serve the frontend from the container (FastAPI already does this).
5. **Fix dependency drift**: make the root `requirements.txt` match `backend/requirements.txt`
   (add `pypdf`, `pymupdf`, `reportlab`). On a container you no longer need Vercel's lambda limits.

> ✅ **Foundation already done** — schema, renderer, designer, and routes are committed (Section 2).

### Phase 1 — Wire the workbook builder into the UI *(highest user value, do next)*
1. In `frontend/js/app.js`, after a successful extraction add a **"Generate Polished Workbook"** action.
2. Add an **intent** input (a small textbox: *"What should this report focus on?"*) and a **theme** picker (corporate / dark / light).
3. Call `POST /api/workbook/design` first to fetch the spec, render a lightweight **preview**
   (sheet tabs, KPI chips, a list of charts, the narrative bullets) in the table panel.
4. On confirm, call `POST /api/workbook/build` via the existing `window.ExcelAI.download()` helper to download the `.xlsx`.
5. Add toolbar buttons in `frontend/js/toolbar.js` under a new **"Report"** ribbon group.

### Phase 2 — Direct URL→Excel and Image→Excel "one-click report" flows
1. Add convenience endpoints that chain existing steps server-side:
   - `POST /api/workbook/from-url` → `scrape_url` → `generate_table` → `build_polished_spec` → `.xlsx`
   - `POST /api/workbook/from-image` (multipart) → `extract_text_from_upload` → `generate_table` → workbook
2. These let a user go from a link/screenshot to a finished report in a single request.
3. Reuse the existing topic-detection step so the user can still pick *which* table to report on.

### Phase 3 — Richer analysis & multi-sheet reports
1. Extend `compute_stats` with **trend** (linear slope) and **anomaly** (z-score / IQR outliers) detection — all deterministic Python.
2. Teach the Groq designer (in `DESIGN_SYSTEM_PROMPT`) to optionally request extra sheets:
   a **"Summary"** sheet (pivot-style aggregates) and a **"Charts"** sheet.
3. Add **pivot-style grouping**: Python groups rows by a chosen dimension and emits an
   aggregated sheet the dashboard charts read from.
4. Add a **"Raw → Cleaned"** option: run your existing cleaning/calculated-columns before building.

### Phase 4 — Persistence, history & quality
1. Add **Postgres** (now possible on the container) for real users + saved reports/projects
   — replaces the in-memory `_DEMO_USERS` dict.
2. Store generated workbooks in object storage (S3/R2) so users have a **history**.
3. Add a **pytest** suite around `workbook_builder` (golden-file checks) and `compute_stats`
   (numeric correctness) — the deterministic design makes this easy.
4. Add **prompt caching / a tiny in-memory cache** keyed on the design input to skip repeat Groq calls.

---

## 5. Cost & reliability notes

- **One small Groq call per report.** Input is schema + sample + stats (hundreds of tokens), output is a compact design (≤2k tokens). Independent of row count.
- **Always-on fallback.** No key, rate limit, or bad JSON → `_default_design` still produces a clean, charted, KPI'd workbook.
- **No code execution, no new packages.** Everything rides on `openpyxl` (already installed) + `groq` (already installed).
- **Deterministic numbers.** Every total/average/growth is computed in Python, so reports are auditable and reproducible.

---

## 6. Open choices for you (when we continue)

1. **Frontend preview depth** — simple (tabs + KPI chips + chart list) vs. richer (render chart thumbnails client-side with a JS chart lib). *Recommend simple first.*
2. **Default theme** — corporate (blue) vs. your existing dark-luxury look. *Renderer supports all three.*
3. **One-click vs. preview-then-build** — auto-download, or always show the design preview first. *Recommend preview-then-build for trust.*
4. **Multi-table reports** — should one URL/image with several tables produce one multi-sheet workbook? *Easy to add in Phase 3.*

> Next recommended step: **Phase 1 (wire the UI)** so you can see polished workbooks end-to-end from the app. Say the word and I'll implement the frontend button, intent/theme inputs, preview panel, and download wiring.
