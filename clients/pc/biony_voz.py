"""Cliente de terminal do Biony: fale (Enter para gravar e Enter para enviar) ou digite.

Configuração (variáveis de ambiente ou no .env da raiz do repositório):
    BIONY_URL        ex.: http://100.111.71.50:8420
    BIONY_API_TOKEN  o mesmo token do servidor

Rodar:
    pip install -r clients/pc/requirements.txt
    python clients/pc/biony_voz.py
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
import sys
import wave

import httpx
import numpy as np
import sounddevice as sd

RATE = 16_000  # o Whisper trabalha em 16 kHz mono
MIN_SECONDS = 0.4
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


def load_config() -> tuple[str, str]:
    values: dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.lstrip().startswith("#"):
                values[key.strip()] = value.strip()
    url = os.environ.get("BIONY_URL") or values.get("BIONY_URL")
    token = os.environ.get("BIONY_API_TOKEN") or values.get("BIONY_API_TOKEN")
    if not url or not token:
        sys.exit("Defina BIONY_URL e BIONY_API_TOKEN (no ambiente ou no .env da raiz).")
    return url.rstrip("/"), token


def record() -> bytes | None:
    chunks: list[np.ndarray] = []

    def on_audio(data: np.ndarray, frames: int, time, status) -> None:
        chunks.append(data.copy())

    with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", callback=on_audio):
        input("  🎙️  gravando... aperte Enter para enviar ")
    audio = np.concatenate(chunks) if chunks else np.zeros((0, 1), dtype=np.int16)
    if len(audio) < RATE * MIN_SECONDS:
        print("  (curto demais, ignorei)")
        return None

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(audio.tobytes())
    return buffer.getvalue()


def play(wav_bytes: bytes) -> None:
    with wave.open(io.BytesIO(wav_bytes)) as wav:
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
        rate = wav.getframerate()
    sd.play(samples, rate)
    sd.wait()


def main() -> None:
    url, token = load_config()
    # A primeira fala pode demorar: o servidor ainda pode estar carregando o Whisper.
    http = httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=120)
    try:
        http.get("/health").raise_for_status()
    except httpx.HTTPError as error:
        sys.exit(f"Não consegui falar com o Biony em {url}: {error}")

    session: str | None = None
    print("Biony conectado. Enter = falar · digite = mandar texto · 'sair' = sair\n")
    while True:
        try:
            line = input("você> ")
        except (EOFError, KeyboardInterrupt):
            break
        if line.strip().lower() in {"sair", "exit", "quit"}:
            break

        try:
            if line.strip():
                response = http.post("/texto", json={"texto": line, "sessao": session})
            else:
                audio = record()
                if audio is None:
                    continue
                print("  ...")
                response = http.post(
                    "/voz",
                    files={"audio": ("fala.wav", audio, "audio/wav")},
                    data={"sessao": session} if session else {},
                )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            print(f"  ⚠️  {error.response.status_code}: {error.response.text}\n")
            continue
        except httpx.HTTPError as error:
            print(f"  ⚠️  sem resposta do servidor: {error}\n")
            continue

        body = response.json()
        session = body["sessao"]
        if "transcricao" in body:
            print(f"  (ouvi: {body['transcricao'] or '—'})")
        print(f"biony> {body['resposta']}\n")
        if body.get("audio_wav_base64"):
            play(base64.b64decode(body["audio_wav_base64"]))


if __name__ == "__main__":
    main()
