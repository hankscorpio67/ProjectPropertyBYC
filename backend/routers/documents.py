import os
import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
import aiosqlite

from ..database import get_db
from ..config import config
from ..services.document_service import DocumentService

router = APIRouter()
_doc_service = DocumentService()

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xlsx",
    "text/plain": "txt",
}

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt"}


@router.post("/upload/{project_id}", status_code=201)
async def upload_document(
    project_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    # Verify project exists
    rows = await db.execute_fetchall("SELECT id FROM projects WHERE id = ?", (project_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate file type
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    file_type = ext.lstrip(".")
    if file_type == "doc":
        file_type = "docx"
    if file_type == "xls":
        file_type = "xlsx"

    # Check size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > config.MAX_UPLOAD_SIZE_MB:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max size: {config.MAX_UPLOAD_SIZE_MB}MB",
        )

    doc_id = str(uuid.uuid4())
    doc_dir = os.path.join(config.projects_dir, project_id, "documents")
    os.makedirs(doc_dir, exist_ok=True)
    save_path = os.path.join(doc_dir, f"{doc_id}{ext}")

    with open(save_path, "wb") as f:
        f.write(content)

    await db.execute(
        """INSERT INTO documents (id, project_id, filename, file_type, file_size, indexed)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (doc_id, project_id, file.filename, file_type, len(content)),
    )
    await db.commit()

    # Index in background
    background_tasks.add_task(_index_document, doc_id, project_id, save_path, file_type)

    rows = await db.execute_fetchall("SELECT * FROM documents WHERE id = ?", (doc_id,))
    return dict(rows[0])


async def _index_document(doc_id: str, project_id: str, file_path: str, file_type: str):
    """Background task: parse file and index chunks into vector store."""
    try:
        chunk_count = await _doc_service.ingest(doc_id, project_id, file_path, file_type)
        # Update DB - open a fresh connection in background task
        async with aiosqlite.connect(config.db_path) as db:
            await db.execute(
                "UPDATE documents SET indexed = 1, chunk_count = ? WHERE id = ?",
                (chunk_count, doc_id),
            )
            await db.commit()
    except Exception as e:
        print(f"[indexing error] doc {doc_id}: {e}")
        async with aiosqlite.connect(config.db_path) as db:
            await db.execute(
                "UPDATE documents SET indexed = 2 WHERE id = ?", (doc_id,)
            )
            await db.commit()


@router.get("/{project_id}")
async def list_documents(project_id: str, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall(
        "SELECT * FROM documents WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    result = []
    for r in rows:
        d = dict(r)
        # indexed: 0=pending, 1=done, 2=error
        d["status"] = {0: "indexing", 1: "ready", 2: "error"}.get(d["indexed"], "unknown")
        result.append(d)
    return result


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, db: aiosqlite.Connection = Depends(get_db)):
    rows = await db.execute_fetchall("SELECT * FROM documents WHERE id = ?", (doc_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Document not found")
    doc = dict(rows[0])

    # Remove from vector store
    await asyncio.get_event_loop().run_in_executor(
        None, _doc_service.delete_document, doc_id, doc["project_id"]
    )

    # Remove file
    ext = f".{doc['file_type']}"
    file_path = os.path.join(
        config.projects_dir, doc["project_id"], "documents", f"{doc_id}{ext}"
    )
    if os.path.exists(file_path):
        os.remove(file_path)

    await db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    await db.commit()
