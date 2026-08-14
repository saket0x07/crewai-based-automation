import os
import io
import tempfile
from typing import Dict, Any, Optional

# Lazy loading global for faster-whisper model
_faster_whisper_model = None


def get_faster_whisper_model():
    """
    Singleton lazy-loader for local Faster-Whisper model.
    Model size can be controlled via environment variable WHISPER_MODEL_SIZE (default: 'base.en').
    """
    global _faster_whisper_model
    if _faster_whisper_model is None:
        model_size = os.getenv("WHISPER_MODEL_SIZE", "base.en")
        print(f"[AudioTranscriber] Initializing local Faster-Whisper model ('{model_size}')...")
        try:
            from faster_whisper import WhisperModel
            # Using CPU with int8 quantization for fast, low-memory inference
            _faster_whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
            print(f"[AudioTranscriber] Faster-Whisper model ('{model_size}') loaded successfully.")
        except Exception as e:
            print(f"[AudioTranscriber Error] Failed to initialize Faster-Whisper model: {e}")
            _faster_whisper_model = None
    return _faster_whisper_model


def transcribe_audio_file(
    file_bytes: bytes,
    filename: str = "audio_answer.webm",
    live_transcript: Optional[str] = None
) -> Dict[str, Any]:
    """
    Transcribes candidate audio notes into text using high-accuracy Faster-Whisper:
    1. If file_bytes is provided, transcribes locally via Faster-Whisper (with technical domain prompt).
    2. If OPENAI_API_KEY (sk-...) is set, can optionally fall back to cloud Whisper.
    3. If local transcription is empty/fails, falls back to captured live_transcript from browser.
    """
    cleaned_live = (live_transcript or "").strip()

    if not file_bytes:
        return {
            "transcript": cleaned_live or "No audio recorded.",
            "language": "en",
            "duration_seconds": 0.0,
            "confidence": 0.0
        }

    # Determine file extension
    ext = os.path.splitext(filename)[1].lower() or ".webm"
    if not ext.startswith("."):
        ext = f".{ext}"

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        temp_file.write(file_bytes)
        temp_file.flush()
        temp_file.close()

        # 1. Try local Faster-Whisper model first (Zero Cost, High Accuracy)
        whisper_model = get_faster_whisper_model()
        if whisper_model is not None:
            # Technical domain prompt to boost accuracy for engineering terminology
            technical_prompt = (
                "Technical mock interview response discussing Python, FastAPI, PySpark, "
                "PostgreSQL, Docker, FAISS, CrewAI, Kubernetes, SQL, microservices, and REST APIs."
            )
            segments, info = whisper_model.transcribe(
                temp_file.name,
                beam_size=5,
                initial_prompt=technical_prompt,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            transcript_text = " ".join([segment.text for segment in segments]).strip()

            # Clean common silent audio hallucinations
            lower_clean = transcript_text.strip(" .").lower()
            hallucinations = ["none", "thank you", "thank you for watching", "subtitles by", "bye", ""]
            if lower_clean not in hallucinations and len(transcript_text) > 2:
                print(f"[AudioTranscriber] Local Faster-Whisper transcript ({info.language}): '{transcript_text[:60]}...'")
                return {
                    "transcript": transcript_text,
                    "language": info.language or "en",
                    "duration_seconds": round(info.duration, 2),
                    "confidence": 0.98
                }

        # 2. Check for Cloud OpenAI API key if local Faster-Whisper was empty/unavailable
        openai_key = os.getenv("OPENAI_API_KEY", "").strip()
        if openai_key and not openai_key.startswith("sk-or-") and not openai_key.startswith("mock"):
            import openai
            client = openai.OpenAI(api_key=openai_key)
            with open(temp_file.name, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="json"
                )
            transcript_text = getattr(response, "text", "") or (response.get("text", "") if isinstance(response, dict) else "")
            final_text = transcript_text.strip()
            if final_text.lower() not in ["none", "thank you", "thank you for watching", ""]:
                return {
                    "transcript": final_text,
                    "language": "en",
                    "duration_seconds": round(len(file_bytes) / 16000.0, 2),
                    "confidence": 0.98
                }

    except Exception as e:
        print(f"[AudioTranscriber Warning]: Faster-Whisper processing error ({e}). Using fallback.")
    finally:
        if os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except Exception:
                pass

    # 3. Final Fallback: use live_transcript captured from browser
    fallback_text = cleaned_live or "No spoken transcript recorded."
    print(f"[AudioTranscriber] Using browser transcript fallback: '{fallback_text[:60]}...'")
    return {
        "transcript": fallback_text,
        "language": "en",
        "duration_seconds": round(len(file_bytes) / 16000.0, 2),
        "confidence": 0.85
    }


