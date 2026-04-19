import subprocess
import tempfile
import os
import whisper

_model = None


def transcribe(audio_path: str) -> str:
    global _model
    print(f"🎙️  Transcribing: {audio_path}")
    print(f"   File exists: {os.path.exists(audio_path)}")

    # Convert to WAV first (handles CAF/Opus from iMessage voice memos)
    wav_path = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path],
            check=True, capture_output=True
        )
        print(f"   Converted to WAV: {wav_path}")
    except subprocess.CalledProcessError as e:
        print(f"   ffmpeg error: {e.stderr.decode()}")
        raise

    if _model is None:
        print("   Loading Whisper model...")
        _model = whisper.load_model("base")

    result = _model.transcribe(wav_path)
    os.unlink(wav_path)
    text = result["text"].strip()
    print(f"   Transcribed: {text}")
    return text
