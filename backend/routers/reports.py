import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import Optional
import aiosqlite

from ..database import get_db
from ..config import config
from ..services.report_service import generate_report, list_reports, REPORT_PROMPTS

router = APIRouter()


class ReportRequest(BaseModel):
    project_id: str
    report_type: str
    custom_instructions: Optional[str] = None


@router.get("/types")
async def get_report_types():
    return [
        {"id": k, "label": k.replace("_", " ").title()}
        for k in REPORT_PROMPTS.keys()
    ]


@router.post("/generate")
async def create_report(body: ReportRequest, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall(
        "SELECT * FROM projects WHERE id = ?", (body.project_id,)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")
    project = dict(rows[0])

    if body.report_type not in REPORT_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid report type. Valid: {list(REPORT_PROMPTS.keys())}",
        )

    content, filename = await generate_report(
        project_id=body.project_id,
        project_name=project["name"],
        project_description=project.get("description", ""),
        report_type=body.report_type,
        custom_instructions=body.custom_instructions,
    )

    return {
        "filename": filename,
        "content": content,
        "project_id": body.project_id,
    }


@router.get("/{project_id}")
async def get_reports(project_id: str, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT id FROM projects WHERE id = ?", (project_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")
    return list_reports(project_id)


@router.get("/{project_id}/{filename}")
async def download_report(project_id: str, filename: str):
    # Security: prevent path traversal
    if ".." in filename or "/" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    filepath = os.path.join(config.projects_dir, project_id, "reports", filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Report not found")
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
