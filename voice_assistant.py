"""
voice_assistant.py
------------------
Voice pipeline for the FIPSAR Prospect Journey Intelligence assistant.

Pipeline (matches architecture):
  1. transcribe_audio()  — User audio  →  OpenAI Whisper  →  text transcript
  2. (caller runs text through FIPSAR LangGraph agent)
  3. text_to_speech()    — AI response text  →  gpt-4o-mini-tts  →  audio bytes

Both functions are stateless and safe to call from any Streamlit session.
"""

from __future__ import annotations

import io
import logging

from openai import OpenAI

from config import app_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared OpenAI client
# ---------------------------------------------------------------------------

_client = OpenAI(api_key=app_config.openai_api_key)

# TTS voice options: alloy, echo, fable, onyx, nova, shimmer
_DEFAULT_VOICE = "alloy"

# ---------------------------------------------------------------------------
# Step 1 — Transcribe audio with Whisper
# ---------------------------------------------------------------------------

def transcribe_audio(audio_bytes: bytes, filename: str = "recording.wav") -> str:
    """
    Send raw audio bytes to OpenAI Whisper and return the transcribed text.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio data from st.audio_input (WAV format).
    filename : str
        Filename hint sent to the Whisper API — affects format detection.

    Returns
    -------
    str
        Transcribed text, or empty string on failure.
    """
    if not audio_bytes:
        return ""

    try:
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename  # Whisper uses the name to detect format

        transcript = _client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="en",
            response_format="text",
        )
        text = str(transcript).strip()
        logger.info("Whisper transcription: %s", text[:120])
        return text

    except Exception as exc:
        logger.error("Whisper transcription failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Step 3 — Convert AI response text to speech
# ---------------------------------------------------------------------------

def text_to_speech(
    text: str,
    voice: str = _DEFAULT_VOICE,
    model: str = "gpt-4o-mini-tts",
    speed: float = 1.0,
) -> bytes | None:
    """
    Convert a text string to speech audio using OpenAI TTS.

    Parameters
    ----------
    text : str
        The AI response text to speak.
    voice : str
        OpenAI voice name (alloy / echo / fable / onyx / nova / shimmer).
    model : str
        TTS model — gpt-4o-mini-tts (default) or tts-1 / tts-1-hd as fallback.
    speed : float
        Playback speed multiplier (0.25–4.0).

    Returns
    -------
    bytes | None
        MP3 audio bytes, or None on failure.
    """
    if not text:
        return None

    # Truncate very long responses to avoid TTS token limits (~4096 chars)
    spoken_text = _prepare_text_for_speech(text)

    try:
        response = _client.audio.speech.create(
            model=model,
            voice=voice,
            input=spoken_text,
            speed=speed,
            response_format="mp3",
        )
        audio_bytes = response.content
        logger.info("TTS generated %d bytes for text of length %d", len(audio_bytes), len(spoken_text))
        return audio_bytes

    except Exception as exc:
        logger.warning("TTS with model %s failed: %s — retrying with tts-1", model, exc)
        # Fallback to tts-1 if gpt-4o-mini-tts is unavailable in the account
        try:
            response = _client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=spoken_text,
                speed=speed,
                response_format="mp3",
            )
            return response.content
        except Exception as exc2:
            logger.error("TTS fallback also failed: %s", exc2)
            return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _prepare_text_for_speech(text: str, max_chars: int = 3500) -> str:
    """
    Strip markdown formatting and truncate to a speakable length.
    TTS does not render markdown — asterisks, pipes, and hashes sound bad spoken aloud.
    """
    import re

    # Remove markdown table pipes and dashes
    text = re.sub(r"\|[-:]+\|[-:|\s]+", " ", text)
    text = re.sub(r"\|", " ", text)

    # Remove markdown headers (#, ##, ###)
    text = re.sub(r"^#{1,4}\s+", "", text, flags=re.MULTILINE)

    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)

    # Remove backtick code spans
    text = re.sub(r"`[^`]+`", "", text)

    # Collapse multiple newlines into one
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Trim
    text = text.strip()

    if len(text) > max_chars:
        # Cut at last sentence boundary before the limit
        cut = text[:max_chars].rfind(".")
        if cut > max_chars * 0.6:
            text = text[:cut + 1] + " … response truncated for audio."
        else:
            text = text[:max_chars] + " … response truncated for audio."

    return text
