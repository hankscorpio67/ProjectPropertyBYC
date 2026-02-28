#!/usr/bin/env python3
"""
Strategic Property AI Assistant
Run with: python run.py
Then open http://localhost:8000 in your browser.
"""
import os
import sys


def check_env():
    """Warn if required keys are missing."""
    from dotenv import load_dotenv
    load_dotenv()
    missing = []
    if not os.getenv("ANTHROPIC_API_KEY"):
        missing.append("ANTHROPIC_API_KEY")
    if not os.getenv("BRAVE_SEARCH_API_KEY"):
        missing.append("BRAVE_SEARCH_API_KEY (web search will be disabled)")
    if missing:
        print("⚠️  Missing environment variables:")
        for m in missing:
            print(f"   - {m}")
        print("   Copy .env.example to .env and add your keys.\n")
        if "ANTHROPIC_API_KEY" in missing:
            print("ANTHROPIC_API_KEY is required. Exiting.")
            sys.exit(1)


if __name__ == "__main__":
    check_env()
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    print(f"\n🏗️  Strategic Property AI Assistant")
    print(f"   Running at http://localhost:{port}")
    print(f"   Press Ctrl+C to stop\n")
    uvicorn.run(
        "backend.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="warning",
    )
