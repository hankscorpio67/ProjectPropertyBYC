"""
Chat router: SSE streaming endpoint + history retrieval.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import aiosqlite

from ..database import get_db
from ..config import config
from ..services.claude_service import stream_chat, generate_summary
from ..services.document_service import DocumentService

router = APIRouter()
_doc_service = DocumentService()

SUMMARY_THRESHOLD = 20  # Summarise after this many messages since last summary


class ChatRequest(BaseModel):
    project_id: str
    message: str


@router.post("/stream")
async def chat_stream(body: ChatRequest, db: aiosqlite.Connection = Depends(get_db)):
    # Verify project exists
    rows = await db.execute_fetchall(
        "SELECT * FROM projects WHERE id = ?", (body.project_id,)
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")
    project = dict(rows[0])

    # Save user message
    await db.execute(
        "INSERT INTO messages (project_id, role, content) VALUES (?, ?, ?)",
        (body.project_id, "user", body.message),
    )
    await db.commit()

    # Load message history
    all_messages = await db.execute_fetchall(
        """SELECT id, role, content, created_at FROM messages
           WHERE project_id = ? ORDER BY created_at ASC""",
        (body.project_id,),
    )
    all_messages = [dict(m) for m in all_messages]

    # Load or generate conversation summary for older messages
    summary = None
    summary_row = await db.execute_fetchall(
        "SELECT summary, up_to_msg_id FROM conversation_summaries WHERE project_id = ?",
        (body.project_id,),
    )
    if summary_row:
        summary_data = dict(summary_row[0])
        summary = summary_data["summary"]
        summarised_up_to = summary_data["up_to_msg_id"]
        # Messages after the summary
        recent_messages = [m for m in all_messages if m["id"] > summarised_up_to]
    else:
        summarised_up_to = 0
        recent_messages = all_messages

    # Check if we need a new summary
    messages_since_summary = len([m for m in recent_messages if m["role"] != "user" or m["content"] != body.message])
    if messages_since_summary > SUMMARY_THRESHOLD and len(all_messages) > SUMMARY_THRESHOLD:
        # Summarise everything up to (but not including) the last CONTEXT_MESSAGES messages
        to_summarise = all_messages[:-config.CONTEXT_MESSAGES]
        if to_summarise:
            new_summary = await generate_summary(to_summarise, project["name"])
            last_summarised_id = to_summarise[-1]["id"]
            await db.execute(
                """INSERT INTO conversation_summaries (project_id, summary, up_to_msg_id)
                   VALUES (?, ?, ?)
                   ON CONFLICT(project_id) DO UPDATE SET summary=excluded.summary, up_to_msg_id=excluded.up_to_msg_id""",
                (body.project_id, new_summary, last_summarised_id),
            )
            await db.commit()
            summary = new_summary
            recent_messages = all_messages[-config.CONTEXT_MESSAGES:]

    # Use the last CONTEXT_MESSAGES messages for verbatim context
    context_messages = recent_messages[-config.CONTEXT_MESSAGES:]

    # Retrieve relevant document chunks for this query
    doc_chunks = await _doc_service.search(body.project_id, body.message)

    # Prepare messages in role/content format
    formatted_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in context_messages
        if m["role"] in ("user", "assistant")
    ]

    async def generate():
        full_response = ""
        try:
            async for chunk in stream_chat(
                project_name=project["name"],
                project_description=project.get("description", ""),
                messages=formatted_messages,
                doc_chunks=doc_chunks,
                summary=summary,
            ):
                # Accumulate text for saving
                if chunk.startswith("data: "):
                    try:
                        payload = json.loads(chunk[6:])
                        if payload.get("type") == "text":
                            full_response += payload.get("content", "")
                    except json.JSONDecodeError:
                        pass
                yield chunk
        finally:
            # Save assistant response to DB
            if full_response.strip():
                async with aiosqlite.connect(config.db_path) as save_db:
                    await save_db.execute(
                        "INSERT INTO messages (project_id, role, content) VALUES (?, ?, ?)",
                        (body.project_id, "assistant", full_response.strip()),
                    )
                    await save_db.execute(
                        "UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (body.project_id,),
                    )
                    await save_db.commit()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{project_id}/history")
async def get_history(
    project_id: str,
    limit: int = 50,
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await db.execute_fetchall(
        """SELECT id, role, content, created_at FROM messages
           WHERE project_id = ? ORDER BY created_at DESC LIMIT ?""",
        (project_id, limit),
    )
    messages = list(reversed([dict(r) for r in rows]))
    # Get summary if exists
    summary_rows = await db.execute_fetchall(
        "SELECT summary FROM conversation_summaries WHERE project_id = ?",
        (project_id,),
    )
    summary = dict(summary_rows[0])["summary"] if summary_rows else None
    return {"messages": messages, "summary": summary}


@router.delete("/{project_id}/history", status_code=204)
async def clear_history(project_id: str, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM messages WHERE project_id = ?", (project_id,))
    await db.execute("DELETE FROM conversation_summaries WHERE project_id = ?", (project_id,))
    await db.commit()
