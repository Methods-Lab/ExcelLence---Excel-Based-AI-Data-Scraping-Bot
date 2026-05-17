from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from backend.models.schemas import ExportRequest, UserResponse
from backend.routes.auth import require_current_user

router = APIRouter(prefix="/api/export", tags=["export"])


def generate_pdf_bytes(columns: list[dict], rows: list[list], filename: str | None = None) -> bytes:
    buffer = BytesIO()
    pagesize = landscape(A4) if len(columns) > 5 else A4
    doc = SimpleDocTemplate(buffer, pagesize=pagesize, leftMargin=36, rightMargin=36, topMargin=72, bottomMargin=54)

    styles = getSampleStyleSheet()
    story = []

    # Prepare table data with header row
    header = [col.get("name", f"Col {i+1}") for i, col in enumerate(columns)]
    data = [header]
    for r in rows:
        row = []
        for val in r:
            row.append("" if val is None else str(val))
        data.append(row)

    # Create table
    table = Table(data, repeatRows=1)
    tbl_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor('#E8F5EC')),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor('#155C2B')),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor('#E1E4E8')),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
    ])
    table.setStyle(tbl_style)

    story.append(table)

    def _header_footer(canvas, doc):
        canvas.saveState()
        # Header: left logo text, right timestamp
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(colors.HexColor('#1A1D23'))
        canvas.drawString(36, doc.pagesize[1] - 36, "ExcelLence Export")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor('#4B5563'))
        canvas.drawRightString(doc.pagesize[0] - 36, doc.pagesize[1] - 32, datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
        # Footer: page number
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor('#6B7280'))
        page_number_text = f"Page {doc.page}"
        canvas.drawRightString(doc.pagesize[0] - 36, 30, page_number_text)
        canvas.restoreState()

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    buffer.seek(0)
    return buffer.read()


@router.post("/pdf")
def export_pdf(payload: ExportRequest, user: UserResponse = Depends(require_current_user)) -> StreamingResponse:
    try:
        pdf_bytes = generate_pdf_bytes(payload.columns, payload.rows, payload.filename)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc

    filename = payload.filename or "ExcelLence_Export.pdf"
    if not filename.lower().endswith('.pdf'):
        filename += '.pdf'
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([pdf_bytes]), media_type='application/pdf', headers=headers)
