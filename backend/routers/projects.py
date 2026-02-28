import os
import uuid
import shutil
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import aiosqlite

from ..database import get_db
from ..config import config

router = APIRouter()


class ProjectCreate(BaseModel):
    name: str
    description: str = ""


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


@router.get("")
async def list_projects(db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("""
        SELECT p.id, p.name, p.description, p.created_at, p.updated_at,
               COUNT(DISTINCT d.id) as doc_count,
               COUNT(DISTINCT m.id) as msg_count,
               MAX(m.created_at) as last_message_at
        FROM projects p
        LEFT JOIN documents d ON d.project_id = p.id
        LEFT JOIN messages m ON m.project_id = p.id
        GROUP BY p.id
        ORDER BY p.updated_at DESC
    """)
    return [dict(r) for r in rows]


@router.post("", status_code=201)
async def create_project(body: ProjectCreate, db: aiosqlite.Connection = Depends(get_db)):
    project_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO projects (id, name, description) VALUES (?, ?, ?)",
        (project_id, body.name.strip(), body.description.strip()),
    )
    await db.commit()
    # Create project directories
    project_dir = os.path.join(config.projects_dir, project_id)
    os.makedirs(os.path.join(project_dir, "documents"), exist_ok=True)
    row = await db.execute_fetchall(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    )
    return dict(row[0])


@router.get("/{project_id}")
async def get_project(project_id: str, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall(
        """SELECT p.*, COUNT(DISTINCT d.id) as doc_count, COUNT(DISTINCT m.id) as msg_count
           FROM projects p
           LEFT JOIN documents d ON d.project_id = p.id
           LEFT JOIN messages m ON m.project_id = p.id
           WHERE p.id = ?
           GROUP BY p.id""",
        (project_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")
    return dict(rows[0])


@router.put("/{project_id}")
async def update_project(
    project_id: str, body: ProjectUpdate, db: aiosqlite.Connection = Depends(get_db)
):
    rows = await db.execute_fetchall(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")
    project = dict(rows[0])
    name = body.name.strip() if body.name else project["name"]
    description = body.description.strip() if body.description is not None else project["description"]
    await db.execute(
        "UPDATE projects SET name = ?, description = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (name, description, project_id),
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM projects WHERE id = ?", (project_id,))
    return dict(rows[0])


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")
    # Delete messages, documents, project
    await db.execute("DELETE FROM messages WHERE project_id = ?", (project_id,))
    await db.execute("DELETE FROM documents WHERE project_id = ?", (project_id,))
    await db.execute("DELETE FROM conversation_summaries WHERE project_id = ?", (project_id,))
    await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    await db.commit()
    # Remove files
    project_dir = os.path.join(config.projects_dir, project_id)
    if os.path.exists(project_dir):
        shutil.rmtree(project_dir)
