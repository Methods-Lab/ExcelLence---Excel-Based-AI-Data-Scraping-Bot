from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from backend.routes.auth import require_current_user
from backend.models.schemas import (
    ExtractResponse,
    ImageExtractResponse,
    TextExtractRequest,
    UrlExtractRequest,
    UserResponse,
    TopicDetectRequest,
    TopicDetectResponse,
    SelectedTopicsRequest,
)
from backend.services.groq_service import generate_table, extract_large_dataset, apply_calculated_columns
from backend.services.ocr_service import extract_text_from_upload
from backend.services.ocr_service import extract_text_from_upload
from backend.services.scraper_service import scrape_url

router = APIRouter(prefix="/api/extract", tags=["extract"])


@router.post("/detect-topics", response_model=TopicDetectResponse)
async def detect_topics(payload: TopicDetectRequest, user: UserResponse = Depends(require_current_user)) -> TopicDetectResponse:
    """Detect candidate topics / sub-tables before running full extraction.
    For URLs we use the scraper to find up to 5 tables. For images we use simple heuristics on provided text.
    """
    if payload.content_type == "url":
        try:
            scraped = await scrape_url(payload.content)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        # scraper returns up to 5 tables embedded as TABLE 1: ... blocks
        content = scraped.get("content", "")
        topics = []
        # collect tables
        tables = []
        for part in content.split("TABLE "):
            if part.startswith("1:") or part[:2].isdigit():
                # re-add prefix
                header, *rest = part.split("\n", 1)
                body = rest[0] if rest else ""
                tables.append(body)

        sub_tables = []
        for i, t in enumerate(tables[:10]):
            estimated_rows = max(1, len([r for r in t.splitlines() if r.strip()]) - 1)
            sub_tables.append({"id": f"table_{i+1}", "name": f"Table {i+1}", "estimated_rows": estimated_rows})

        if sub_tables:
            topics.append({"id": "topic_1", "name": scraped.get("title", "Page Tables"), "sub_tables": sub_tables})
        return TopicDetectResponse(topics=topics, scraped_content=scraped.get("content"))

    # image or text heuristics
    # If content looks like OCR text, split lines and estimate potential tables
    lines = [ln for ln in payload.content.splitlines() if ln.strip()]
    est_rows = max(0, len(lines) - 2)
    topics = [{"id": "topic_1", "name": "Detected Tables", "sub_tables": [{"id": "sub_1_1", "name": "Table 1", "estimated_rows": est_rows}]}]
    return TopicDetectResponse(topics=topics)



@router.post('/ocr')
async def ocr_only(file: UploadFile = File(...), user: UserResponse = Depends(require_current_user)) -> dict:
    """Return OCR text for an uploaded image or PDF without running extraction."""
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image file is empty")
    try:
        ocr = await extract_text_from_upload(file_bytes, filename=file.filename)
        return {"text": ocr["text"], "metadata": ocr.get("metadata", {})}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/selected-topics", response_model=ExtractResponse)
async def extract_selected(payload: SelectedTopicsRequest, user: UserResponse = Depends(require_current_user)) -> ExtractResponse:
    """Run extraction on selected sub-tables and apply calculated columns if provided."""
    # For large content, use chunked extraction
    if len(payload.content) > 20000:
        result = await extract_large_dataset(payload.content, {"columns": []})
    else:
        result = generate_table("SELECTED", payload.content)

    rows = result.get("rows", [])
    columns = result.get("columns", [])

    if payload.calculated_columns:
        rows, columns = apply_calculated_columns(rows, columns, payload.calculated_columns)

    return ExtractResponse(
        columns=columns,
        rows=rows,
        confidence=result.get("confidence") or 0.0,
        source_type="TEXT",
        warnings=result.get("warnings", []),
        table_title=result.get("table_title"),
    )


@router.post("/text", response_model=ExtractResponse)
async def extract_text(payload: TextExtractRequest, user: UserResponse = Depends(require_current_user)) -> ExtractResponse:
    # perform extraction
    result = generate_table("TEXT", payload.prompt)

    rows = result.get("rows", [])
    columns = result.get("columns", [])

    # apply calculated columns if provided
    if getattr(payload, "calculated_columns", None):
        rows, columns = apply_calculated_columns(rows, columns, payload.calculated_columns)

    return ExtractResponse(
        columns=columns,
        rows=rows,
        confidence=result.get("confidence") or 0.0,
        source_type="TEXT",
        warnings=result.get("warnings", []),
        table_title=result.get("table_title"),
    )


@router.post("/image", response_model=ImageExtractResponse)
async def extract_image(
    file: UploadFile = File(...),
    instruction: str = Form(""),
    user: UserResponse = Depends(require_current_user),
) -> ImageExtractResponse:
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image file is empty")

    try:
        ocr = await extract_text_from_upload(file_bytes, filename=file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    result = generate_table("IMAGE", ocr["text"], instruction=instruction)
    return ImageExtractResponse(
        columns=result["columns"],
        rows=result["rows"],
        confidence=result["confidence"],
        source_type="IMAGE",
        warnings=result.get("warnings", []),
        table_title=result.get("table_title"),
        ocr_raw_text=ocr["text"],
    )


@router.post("/url", response_model=ExtractResponse)
async def extract_url(payload: UrlExtractRequest, user: UserResponse = Depends(require_current_user)) -> ExtractResponse:
    try:
        scraped = await scrape_url(str(payload.url))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unable to scrape URL: {exc}") from exc

    result = generate_table("URL", scraped["content"], clarification=payload.clarification or scraped["title"])
    return ExtractResponse(
        columns=result["columns"],
        rows=result["rows"],
        confidence=result["confidence"],
        source_type="URL",
        warnings=result.get("warnings", []),
        table_title=result.get("table_title") or scraped["title"],
    )
