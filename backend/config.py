import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    BRAVE_SEARCH_API_KEY: str = os.getenv("BRAVE_SEARCH_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    PORT: int = int(os.getenv("PORT", "8000"))
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
    DATA_DIR: str = os.getenv("DATA_DIR", "./data")
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
    SEARCH_RESULTS_COUNT: int = int(os.getenv("SEARCH_RESULTS_COUNT", "5"))
    CONTEXT_MESSAGES: int = int(os.getenv("CONTEXT_MESSAGES", "15"))
    RETRIEVAL_CHUNKS: int = int(os.getenv("RETRIEVAL_CHUNKS", "6"))

    @property
    def db_path(self) -> str:
        return os.path.join(self.DATA_DIR, "app.db")

    @property
    def projects_dir(self) -> str:
        return os.path.join(self.DATA_DIR, "projects")

    @property
    def chroma_dir(self) -> str:
        return os.path.join(self.DATA_DIR, "chroma")


config = Config()
