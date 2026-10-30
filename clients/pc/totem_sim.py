"""Totem simulado: faz no PC exatamente o que o ESP32 vai fazer, pelo WebSocket /ws/dispositivo.

Enter faz o papel do wake word ("Biony"): começa a gravar e manda o áudio em tempo real
(PCM 16 bits, 16 kHz) enquanto você fala; Enter de novo termina. A resposta chega em pedaços
de PCM e é tocada no alto-falante. Digitar algo manda como texto.

Configuração: BIONY_URL e BIONY_API_TOKEN (ambiente ou .env da raiz), como o biony_voz.py.

    pip install -r clients/pc/requirements.txt
    python clients/pc/totem_sim.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import sounddevice as sd
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
MIC_RATE = 16_000
BLOCK = 1024  # amostras por pedaço (~64 ms), parecido com o que o ESP32 vai mandar


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
    ws_url = url.rstrip("/").replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    return ws_url + "/ws/dispositivo", token


class Totem:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.recording = False
        self.speech = bytearray()
        self.speech_rate = 22050
        self.started = 0.0
        self.idle = asyncio.Event()
        self.idle.set()

    async def listen_server(self) -> None:
        """Recebe tudo o que o servidor manda (como o loop principal do ESP32)."""
        async for message in self.ws:
            if isinstance(message, bytes):
                self.speech.extend(message)
                continue
            data = json.loads(message)
            kind = data.get("tipo")
            elapsed = f"{time.perf_counter() - self.started:5.1f}s" if self.started else "     "
            if kind == "estado":
                print(f"  [{elapsed}] rosto: {data['estado']}")
                if data["estado"] == "ocioso":
                    self.idle.set()
            elif kind == "transcricao":
                print(f"  [{elapsed}] ouvi: {data['texto'] or '(nada)'}")
            elif kind == "resposta":
                confirm = "  (esperando sim/não)" if data["aguardando_confirmacao"] else ""
                print(f"  [{elapsed}] biony ({data['emocao']}): {data['texto']}{confirm}")
                if not data.get("audio"):
                    self.idle.set()
            elif kind == "audio_inicio":
                self.speech.clear()
                self.speech_rate = data["taxa"]
            elif kind == "audio_fim":
                print(f"  [{elapsed}] falando ({len(self.speech) / 2 / self.speech_rate:.1f} s de áudio)")
                await asyncio.to_thread(self.play, bytes(self.speech))
                self.idle.set()
            elif kind == "erro":
                print(f"  [{elapsed}] ⚠️  {data['mensagem']}")
                self.idle.set()

    def play(self, pcm: bytes) -> None:
        sd.play(np.frombuffer(pcm, dtype=np.int16), self.speech_rate)
        sd.wait()

    async def talk(self) -> None:
        """Grava e manda o áudio em pedaços enquanto grava, sem esperar terminar."""
        loop = asyncio.get_running_loop()
        chunks: asyncio.Queue[bytes | None] = asyncio.Queue()

        def on_audio(data, frames, time_info, status) -> None:
            loop.call_soon_threadsafe(chunks.put_nowait, bytes(data))

        async def sender() -> None:
            while (chunk := await chunks.get()) is not None:
                await self.ws.send(chunk)

        await self.ws.send(json.dumps({"tipo": "ouvir_inicio"}))
        sending = asyncio.create_task(sender())
        with sd.RawInputStream(samplerate=MIC_RATE, channels=1, dtype="int16", blocksize=BLOCK, callback=on_audio):
            await asyncio.to_thread(input, "  🎙️  gravando (mandando ao vivo)... Enter para terminar ")
        chunks.put_nowait(None)
        await sending
        self.started = time.perf_counter()
        await self.ws.send(json.dumps({"tipo": "ouvir_fim"}))

    async def run(self) -> None:
        receiver = asyncio.create_task(self.listen_server())
        print("Totem conectado. Enter = \"Biony\" (falar) · digite = texto · 'sair' = sair\n")
        try:
            while not receiver.done():
                await self.idle.wait()
                line = await asyncio.to_thread(input, "totem> ")
                if line.strip().lower() in {"sair", "exit", "quit"}:
                    break
                self.idle.clear()
                if line.strip():
                    self.started = time.perf_counter()
                    await self.ws.send(json.dumps({"tipo": "texto", "texto": line}))
                else:
                    await self.talk()
        finally:
            receiver.cancel()


async def main() -> None:
    url, token = load_config()
    print(f"Conectando em {url} ...")
    try:
        async with connect(url, max_size=None, ping_interval=20) as ws:
            await ws.send(json.dumps({"tipo": "ola", "token": token, "dispositivo": "pc-simulado", "versao": 1}))
            hello = json.loads(await ws.recv())
            if hello.get("tipo") != "ola_ok":
                sys.exit(f"Recusado: {hello.get('mensagem', hello)}")
            print(f"Sessão {hello['sessao']} · voz {hello['voz']}")
            await Totem(ws).run()
    except (OSError, ConnectionClosed) as error:
        sys.exit(f"Conexão perdida: {error}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
