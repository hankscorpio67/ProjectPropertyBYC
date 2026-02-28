from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx
import io

from ..config import config

router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    voice: str = "alloy"  # OpenAI voices: alloy, echo, fable, onyx, nova, shimmer


@router.post("/synthesize")
async def synthesize_speech(body: TTSRequest):
    """Server-side TTS using OpenAI API for higher quality car audio."""
    if not config.OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key not configured. Using browser TTS instead.",
        )

    # Truncate very long texts (TTS has a limit and long responses are better chunked)
    text = body.text[:4000]

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={
                "Authorization": f"Bearer {config.OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "tts-1",
                "input": text,
                "voice": body.voice,
                "response_format": "mp3",
            },
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="TTS API error")

        audio_data = resp.content

    return StreamingResponse(
        io.BytesIO(audio_data),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=speech.mp3"},
    )


@router.get("/config")
async def get_voice_config():
    """Tell frontend which TTS modes are available."""
    return {
        "server_tts_available": bool(config.OPENAI_API_KEY),
        "browser_tts_available": True,  # Always available
    }
