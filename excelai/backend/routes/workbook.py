"""Polished workbook generation — turns extracted data into a designed .xlsx report."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from backend.models.schemas import UserResponse
from backend.models.workbook_schemas import WorkbookBuildRequest
from backend.routes.auth import require_current_user
from backend.services.workbook_ai import build_polished_spec
from backend.services.workbook_builder import build_workbook

router = APIRouter(prefix="/api/workbook", tags=["workbook"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/design")
def design_workbook(payload: WorkbookBuildRequest, user: UserResponse = Depends(require_current_user)) -> dict:
    """Return the workbook spec (sheets, KPIs, charts, narrative) as JSON for preview."""
    try:
        spec = build_polished_spec(
            columns=[c.model_dump() for c in payload.columns],
            rows=payload.rows,
            intent=payload.intent,
            theme=payload.theme,
            title=payload.filename,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Design failed: {exc}") from exc
    return spec.model_dump()


@router.post("/build")
def build(payload: WorkbookBuildRequest, user: UserResponse = Depends(require_current_user)) -> StreamingResponse:
    """Design + render a polished workbook and stream it back as a download."""
    try:
        spec = build_polished_spec(
            columns=[c.model_dump() for c in payload.columns],
            rows=payload.rows,
            intent=payload.intent,
            theme=payload.theme,
            title=payload.filename,
        )
        workbook_bytes, filename = build_workbook(spec, payload.filename)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Workbook build failed: {exc}") from exc

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([workbook_bytes]), media_type=_XLSX_MEDIA_TYPE, headers=headers)
