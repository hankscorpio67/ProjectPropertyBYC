import os
import aiosqlite
from .config import config

DB_PATH = config.db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT DEFAULT '',
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    tokens_used INTEGER DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL REFERENCES projects(id),
    filename    TEXT NOT NULL,
    file_type   TEXT NOT NULL,
    file_size   INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    indexed     INTEGER DEFAULT 0,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL UNIQUE REFERENCES projects(id),
    summary     TEXT NOT NULL,
    up_to_msg_id INTEGER NOT NULL,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_project ON messages(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_documents_project ON documents(project_id);
"""


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()
