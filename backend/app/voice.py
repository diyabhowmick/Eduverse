"""Eddie's own voice on the server, so every answer sounds like the recorded greetings.

Kokoro (open model, runs on the CPU, no API, nothing leaves the server). Optional: if the model
files or the packages are missing, /api/voice/status says so and the app falls back to the
phone's built-in voice. Each sentence is made once and cached.

Setup: pip install -r requirements-voice.txt, then put kokoro-v1.0(.int8).onnx and voices-v1.0.bin
in EDDIE_VOICE_DIR (default ./voice_models). scripts/get_voice_model.sh downloads them.
"""
import hashlib, io, os, re, shutil, subprocess, threading
from pathlib import Path

DIR = Path(os.getenv("EDDIE_VOICE_DIR", Path(__file__).resolve().parent.parent / "voice_models"))
VOICE = os.getenv("EDDIE_VOICE", "am_michael+am_puck:0.35")     # one voice, or a blend a+b:weight
SPEED = float(os.getenv("EDDIE_VOICE_SPEED", "0.88"))
CACHE = Path(os.getenv("EDDIE_VOICE_CACHE", Path(os.getenv("STORAGE_DIR", "/tmp")) / "voice_cache"))
SMOOTH = ("highpass=f=60,equalizer=f=180:t=q:w=1.2:g=2.5,equalizer=f=3200:t=q:w=1.5:g=-2,deesser=i=0.5:m=0.5:f=0.5,"
          "lowpass=f=8200,acompressor=threshold=-22dB:ratio=2:attack=25:release=300,aecho=0.8:0.55:40:0.08,loudnorm=I=-16:TP=-1.5:LRA=8")
_lock = threading.Lock()
_k = None
_why = ""


def _model_file():
    for n in ("kokoro-v1.0.int8.onnx", "kokoro-v1.0.onnx", "kokoro-v1.0.fp16.onnx"):
        if (DIR / n).exists():
            return DIR / n
    return None


def engine():
    global _k, _why
    if _k is not None:
        return _k
    m = _model_file()
    if not m or not (DIR / "voices-v1.0.bin").exists():
        _why = f"Voice model files not found in {DIR}"
        return None
    try:
        from kokoro_onnx import Kokoro
        _k = Kokoro(str(m), str(DIR / "voices-v1.0.bin"))
    except Exception as e:  # packages missing, or the model will not load
        _why = f"Voice engine could not start: {str(e)[:160]}"
        return None
    return _k


def status() -> dict:
    ok = engine() is not None
    return {"ok": ok, "voice": VOICE if ok else "", "why": "" if ok else _why}


def _style(k):
    if "+" in VOICE:
        a, rest = VOICE.split("+", 1); b, w = rest.split(":"); w = float(w)
        return k.get_voice_style(a) * (1 - w) + k.get_voice_style(b) * w
    return VOICE


def clean(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()[:400]
    t = re.sub(r"\bStd\.?\s*(?=\d)", "Standard ", t)
    t = t.replace("EduVerse", "Edu-verse").replace("_____", "blank").replace("______", "blank")
    return t


def say(text: str) -> tuple[bytes, str]:
    """Speech for one sentence or short reply: (audio bytes, mime type). Cached by text and voice."""
    t = clean(text)
    if not t:
        raise ValueError("Nothing to say")
    has_ff = bool(shutil.which("ffmpeg"))
    ext, mime = ("mp3", "audio/mpeg") if has_ff else ("wav", "audio/wav")
    key = hashlib.sha1(f"{VOICE}|{SPEED}|{t}".encode()).hexdigest()
    f = CACHE / f"{key}.{ext}"
    if f.exists():
        return f.read_bytes(), mime
    k = engine()
    if k is None:
        raise RuntimeError(_why or "Voice is not set up")
    import soundfile as sf
    with _lock:
        samples, sr = k.create(t, voice=_style(k), speed=SPEED, lang="en-us" if VOICE[0] == "a" else "en-gb")
    wav = io.BytesIO(); sf.write(wav, samples, sr, format="WAV"); wav = wav.getvalue()
    data = wav
    if has_ff:
        p = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "wav", "-i", "pipe:0", "-af", SMOOTH, "-ar", "24000", "-ac", "1",
                            "-b:a", "96k", "-f", "mp3", "pipe:1"], input=wav, capture_output=True, timeout=60)
        data = p.stdout if p.returncode == 0 and p.stdout else wav
        if data is wav:
            ext, mime = "wav", "audio/wav"; f = CACHE / f"{key}.wav"
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_bytes(data)
    return data, mime
