"""Biony por palavra de ativação no PC: diga "Biony" e fale o comando.

Provisório, enquanto o totem físico não existe (lá a palavra de ativação será detectada no próprio aparelho).

Privacidade: a detecção é LOCAL. Cada frase captada pelo microfone é transcrita aqui, no PC, pelo
faster-whisper; se ela não começa com "Biony", o áudio é descartado na hora e não sai do computador.
Só vai para o servidor a frase que começa com "Biony" e as falas seguintes da mesma conversa.

Configuração: BIONY_URL e BIONY_API_TOKEN (no ambiente ou no .env da raiz), como no biony_voz.py.

Rodar (com janela, para testar):
    pip install -r clients/pc/requirements.txt -r clients/pc/requirements-ativacao.txt
    python clients/pc/biony_ativacao.py            # --help mostra as opções; --debug mostra o que ele ouviu

Em segundo plano, iniciando sozinho quando você entra no Windows (sem janela; log em clients/pc/ativacao.log):
    .\clients\pc\instalar_ativacao.ps1            # -Parar, -Remover
"""

from __future__ import annotations

import argparse
import base64
import collections
import difflib
import io
import math
import re
import socket
import sys
import threading
import time
import unicodedata
import wave
from pathlib import Path

import numpy as np

RATE = 16_000
BLOCK = 320  # 20 ms
WAKE_WORD = "biony"
# Como o Whisper costuma escrever o nome; o resto é pego por semelhança (veja is_wake_word).
WAKE_VARIANTS = {"biony", "bione", "bioni", "bionei", "bioney", "bionie", "bionni", "byoni", "bionhi", "biôni"}
WAKE_SIMILARITY = 0.78
WAKE_SEARCH_WORDS = 4  # só nas primeiras palavras: "Biony, ...", "ei Biony, ...", "boa noite, Biony"
GREETINGS = {"ei", "oi", "ola", "opa", "hey", "hei", "ok", "okay", "fala", "eai", "salve", "e"}  # não são comando
SESSION = "pc-ativacao"
INSTANCE_PORT = 47811  # porta local usada só como trava: duas cópias seriam dois microfones respondendo juntos
RETRY_SECONDS = 15
LOG_LIMIT_BYTES = 1_000_000
BEEP_SECONDS = 0.22
# Texto-guia do Whisper local: com exemplos do nome em frases, o "Biony" sozinho passou de 1/6 para 6/6 acertos.
# Efeito colateral: sobre ruído ele inventa a própria frase-guia, por isso o filtro NO_SPEECH_MAX abaixo.
PROMPT = "Biony. Biony, liga a luz. Ei Biony, que horas são? Biony, boa noite."
NO_SPEECH_MAX = 0.6  # trecho que o próprio Whisper acha que "não é fala" é ignorado


# ------------------------------------------------------------------ palavra de ativação


def plain(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()


def is_wake_word(word: str) -> bool:
    word = plain(word)
    if word in {plain(v) for v in WAKE_VARIANTS}:
        return True
    return len(word) >= 4 and difflib.SequenceMatcher(None, word, WAKE_WORD).ratio() >= WAKE_SIMILARITY


def split_wake(text: str) -> tuple[bool, str]:
    """(ouviu "Biony" no começo?, o comando: o que veio antes e depois do nome, sem cumprimentos)."""
    words = re.findall(r"[\w'-]+", text)
    limit = min(WAKE_SEARCH_WORDS, len(words))
    candidates = [(i, 1, words[i]) for i in range(limit)]
    # O Whisper às vezes separa o nome em duas palavras ("bio ni").
    candidates += [(i, 2, words[i] + words[i + 1]) for i in range(min(WAKE_SEARCH_WORDS - 1, len(words) - 1))]
    for index, span, candidate in candidates:
        if is_wake_word(candidate):
            before = [w for w in words[:index] if plain(w) not in GREETINGS]
            return True, " ".join(before + words[index + span:])
    return False, text


def has_command(command: str) -> bool:
    """Veio algo além do nome ("Biony, liga a luz") ou só "Biony"?"""
    return len(plain(re.sub(r"[^\w]", "", command))) >= 3


# ------------------------------------------------------------------ separar frases pelo volume


class UtteranceDetector:
    """Separa frases no fluxo do microfone: começa na voz, termina no silêncio. Mede o ruído do ambiente."""

    def __init__(
        self,
        *,
        start_blocks: int = 5,       # 100 ms de voz seguidos para começar
        end_silence: float = 0.8,    # silêncio que encerra a frase
        preroll: float = 0.4,        # guarda o começo, antes de a voz passar do limite
        min_voice: float = 0.35,     # menos que isto é estalo, não fala
        max_seconds: float = 15.0,
        floor: float = 0.008,
        ratio: float = 3.5,
        max_noise: float = 0.05,
    ) -> None:
        self.block_seconds = BLOCK / RATE
        self.start_blocks = start_blocks
        self.end_silence = end_silence
        self.min_voice = min_voice
        self.max_seconds = max_seconds
        self.floor, self.ratio, self.max_noise = floor, ratio, max_noise
        self._preroll = collections.deque(maxlen=max(1, int(preroll / self.block_seconds)))
        self.noise = 0.004
        self.reset()

    def calibrate(self, source, seconds: float = 1.0) -> None:
        """Mede o ruído do ambiente (ar-condicionado, ventilador) antes de começar; fique em silêncio."""
        levels = []
        for _ in range(int(seconds / self.block_seconds)):
            block = source.read()
            if block is not None:
                levels.append(float(np.sqrt(np.mean((block.astype(np.float32) / 32768.0) ** 2))))
        if levels:
            self.noise = min(self.max_noise, float(np.median(levels)))

    def reset(self) -> None:
        self.active = False
        self._chunks: list[np.ndarray] = []
        self._loud_run = 0
        self._silence = 0.0
        self._voiced = 0.0
        self._preroll.clear()

    def feed(self, block: np.ndarray) -> np.ndarray | None:
        """Devolve a frase (int16) quando ela termina; senão None."""
        rms = float(np.sqrt(np.mean((block.astype(np.float32) / 32768.0) ** 2)))
        loud = rms > max(self.floor, self.noise * self.ratio)
        if not self.active:
            self._preroll.append(block)
            if loud:
                self._loud_run += 1
                if self._loud_run >= self.start_blocks:
                    self.active = True
                    self._chunks = list(self._preroll)
                    self._silence = 0.0
                    self._voiced = self._loud_run * self.block_seconds
            else:
                self._loud_run = 0
                self.noise = min(self.max_noise, self.noise * 0.98 + rms * 0.02)  # só aprende no silêncio
            return None
        self._chunks.append(block)
        if loud:
            self._silence = 0.0
            self._voiced += self.block_seconds
        else:
            self._silence += self.block_seconds
        if self._silence >= self.end_silence or len(self._chunks) * self.block_seconds >= self.max_seconds:
            audio, voiced = np.concatenate(self._chunks), self._voiced
            if self._silence < self.end_silence:
                # Estourou o tempo sem silêncio: ou é um barulho constante (música, obra) ou fala sem parar.
                # Sobe o limite do ambiente para não ficar preso nele.
                level = float(np.sqrt(np.mean((audio.astype(np.float32) / 32768.0) ** 2)))
                self.noise = min(self.max_noise, max(self.noise, level * 0.7))
            self.reset()
            return audio if voiced >= self.min_voice else None
        return None


def next_utterance(source, detector: UtteranceDetector, max_wait: float | None = None) -> np.ndarray | None:
    """Próxima frase. `max_wait` conta segundos de ÁUDIO sem ninguém começar a falar (None = espera para sempre).

    Levanta EOFError quando a fonte acaba (só acontece em testes com arquivo)."""
    waited = 0.0
    while True:
        block = source.read()
        if block is None:
            continue
        audio = detector.feed(block)
        if audio is not None:
            return audio
        if not detector.active:
            waited += detector.block_seconds
            if max_wait is not None and waited >= max_wait:
                return None


# ------------------------------------------------------------------ o laço principal


def run(source, detector, transcribe, send, beep, say, *, wait: float = 8.0, debug: bool = False) -> None:
    """Espera "Biony"; depois conversa até ficar `wait` segundos sem ninguém falar."""
    try:
        while True:
            phrase = next_utterance(source, detector)
            text = transcribe(phrase)
            heard, rest = split_wake(text)
            if debug:
                say(f"  (ouvi: {text!r} → {'ACORDOU' if heard else 'ignorado'})")
            if not heard:
                continue
            pending = phrase if has_command(rest) else None
            if pending is None:
                beep()
                say("  🎙️  pode falar...")
            while True:
                if pending is None:
                    pending = next_utterance(source, detector, wait)
                    if pending is None:
                        say("  (voltando a esperar o Biony)\n")
                        break
                send(pending)
                pending = None
    except EOFError:
        return


# ------------------------------------------------------------------ áudio, rede e linha de comando


def to_wav(audio: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(audio.astype(np.int16).tobytes())
    return buffer.getvalue()


class BlockQueue:
    """Fila de blocos de áudio. Além de ler e esvaziar, deixa jogar fora só um trecho do meio
    (o bipe que o próprio microfone ouviu) sem perder a fala que já estava esperando na fila."""

    def __init__(self) -> None:
        self._blocks: collections.deque[np.ndarray] = collections.deque()
        self._changed = threading.Condition()

    def put(self, block: np.ndarray) -> None:
        with self._changed:
            self._blocks.append(block)
            self._changed.notify()

    def get(self, timeout: float = 0.5) -> np.ndarray | None:
        with self._changed:
            if not self._blocks:
                self._changed.wait(timeout)
            return self._blocks.popleft() if self._blocks else None

    def mark(self) -> int:
        with self._changed:
            return len(self._blocks)

    def drop_after(self, mark: int, count: int) -> None:
        """Remove `count` blocos a partir da posição `mark` (o que chegou depois dela)."""
        with self._changed:
            for _ in range(count):
                if len(self._blocks) > mark:
                    del self._blocks[mark]

    def clear(self) -> None:
        with self._changed:
            self._blocks.clear()


class MicSource:
    """Microfone em blocos de 20 ms."""

    def __init__(self, device=None) -> None:
        self.queue = BlockQueue()
        self._device = device

    def __enter__(self) -> "MicSource":
        import sounddevice as sd

        def on_audio(data, frames, time_info, status) -> None:
            self.queue.put(data[:, 0].copy())

        self._stream = sd.InputStream(
            samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK, device=self._device, callback=on_audio
        )
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stream.stop()
        self._stream.close()

    def read(self) -> np.ndarray | None:
        return self.queue.get()


def play_wav(wav_bytes: bytes) -> None:
    import sounddevice as sd

    with wave.open(io.BytesIO(wav_bytes)) as wav:
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
        rate = wav.getframerate()
    sd.play(samples, rate)
    sd.wait()


def play_beep() -> None:
    import sounddevice as sd

    t = np.arange(int(RATE * 0.11)) / RATE
    tones = [np.sin(2 * np.pi * f * t) * np.hanning(len(t)) for f in (880, 1175)]
    sd.play((np.concatenate(tones) * 9000).astype(np.int16), RATE)
    sd.wait()


def make_sender(http, play, after_reply=lambda: None, say=print):
    """Função que manda uma frase ao servidor (/voz), mostra a conversa e toca a resposta."""
    import httpx

    def send(audio: np.ndarray) -> dict | None:
        say("  ...")
        try:
            response = http.post(
                "/voz",
                files={"audio": ("fala.wav", to_wav(audio), "audio/wav")},
                data={"sessao": SESSION},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            say(f"  ⚠️  {error.response.status_code}: {error.response.text}\n")
            return None
        except httpx.HTTPError as error:
            say(f"  ⚠️  sem resposta do servidor: {error}\n")
            return None
        body = response.json()
        say(f"  você> {body.get('transcricao') or '—'}")
        say(f"biony> {body['resposta']}\n")
        if body.get("audio_wav_base64"):
            play(base64.b64decode(body["audio_wav_base64"]))
        after_reply()
        return body

    return send


def load_whisper(name: str, gpu: bool):
    from faster_whisper import WhisperModel

    if gpu:
        try:
            model = WhisperModel(name, device="cuda", compute_type="float16")
            list(model.transcribe(np.zeros(RATE, dtype=np.float32), language="pt")[0])  # acha DLL faltando já aqui
            return model
        except Exception as error:  # noqa: BLE001 - qualquer falha da GPU cai para a CPU
            print(f"  (GPU indisponível: {str(error)[:80]}; usando a CPU)")
    return WhisperModel(name, device="cpu", compute_type="int8")


def make_transcriber(model):
    def transcribe(audio: np.ndarray) -> str:
        segments, _ = model.transcribe(
            audio.astype(np.float32) / 32768.0,
            language="pt",
            beam_size=1,
            initial_prompt=PROMPT,
            condition_on_previous_text=False,
        )
        return " ".join(s.text.strip() for s in segments if s.no_speech_prob <= NO_SPEECH_MAX).strip()

    return transcribe


class LogFile:
    """Saída em arquivo com a hora em cada linha (no segundo plano não existe janela para ver o que ele faz)."""

    def __init__(self, path: Path) -> None:
        if path.exists() and path.stat().st_size > LOG_LIMIT_BYTES:
            path.write_text("", encoding="utf-8")  # não deixa crescer para sempre
        self._file = open(path, "a", encoding="utf-8", buffering=1)
        self._at_line_start = True

    def write(self, text: str) -> int:
        for part in text.splitlines(keepends=True):
            if self._at_line_start and part.strip():
                self._file.write(time.strftime("%d/%m %H:%M:%S  "))
            self._file.write(part)
            self._at_line_start = part.endswith("\n")
        return len(text)

    def flush(self) -> None:
        self._file.flush()


def acquire_single_instance() -> socket.socket | None:
    """Trava local: devolve o socket (mantenha-o vivo) ou None se já existe outra cópia rodando."""
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock.bind(("127.0.0.1", INSTANCE_PORT))
    except OSError:
        lock.close()
        return None
    return lock


def wait_for_server(http, url: str, persistent: bool) -> None:
    """Fora do modo persistente, desiste na primeira falha. No segundo plano espera o servidor aparecer
    (ao ligar o PC o Tailscale pode levar um tempo para conectar)."""
    import httpx

    warned = False
    while True:
        try:
            http.get("/health").raise_for_status()
            return
        except httpx.HTTPError as error:
            if not persistent:
                sys.exit(f"Não consegui falar com o Biony em {url}: {error}")
            if not warned:
                print(f"  (esperando o servidor em {url}: {error})")
                warned = True
            time.sleep(RETRY_SECONDS)


def listen_forever(http, transcribe, args) -> None:
    device = int(args.dispositivo) if args.dispositivo and args.dispositivo.isdigit() else args.dispositivo
    with MicSource(device) as mic:
        detector = UtteranceDetector()
        print("Medindo o ruído do ambiente (1 segundo de silêncio)...")
        detector.calibrate(mic)

        def after_reply() -> None:
            mic.queue.clear()  # não ouvir a própria voz dele (nem o que falou enquanto ele respondia)
            detector.reset()

        send = make_sender(http, play_wav, after_reply)

        def beep() -> None:
            # Descarta só o que o microfone ouviu do próprio bipe; se você já começou a falar o comando
            # enquanto o reconhecimento pensava, essa fala continua na fila.
            mark = mic.queue.mark()
            play_beep()
            mic.queue.drop_after(mark, math.ceil((BEEP_SECONDS + 0.15) / detector.block_seconds))

        print('Pronto. Diga "Biony" e fale o comando. Ctrl+C para sair.\n')
        run(mic, detector, transcribe, send, beep, print, wait=args.espera, debug=args.debug)


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Biony por palavra de ativação no PC.")
    parser.add_argument("--modelo", default="small", help="modelo do Whisper local: base (mais rápido), small (padrão)")
    parser.add_argument("--gpu", action="store_true", help="usa a placa de vídeo (NVIDIA) para a detecção")
    parser.add_argument("--espera", type=float, default=8.0, help="segundos de silêncio até voltar a esperar o Biony")
    parser.add_argument("--dispositivo", help="número ou nome do microfone (veja --listar)")
    parser.add_argument("--listar", action="store_true", help="lista os microfones e sai")
    parser.add_argument("--debug", action="store_true", help="mostra o que a detecção local ouviu")
    parser.add_argument("--persistente", action="store_true",
                        help="segundo plano: espera o servidor aparecer e recomeça sozinho se algo falhar")
    parser.add_argument("--log", type=Path, help="grava tudo neste arquivo (necessário sem janela, com pythonw)")
    args = parser.parse_args(argv)

    if args.listar:
        import sounddevice as sd

        print(sd.query_devices())
        return
    if args.log:
        sys.stdout = sys.stderr = LogFile(args.log)
    lock = acquire_single_instance()
    if lock is None:
        sys.exit("O Biony por palavra de ativação já está rodando neste PC.")

    from biony_voz import load_config
    import httpx

    url, token = load_config()
    http = httpx.Client(base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=120)
    wait_for_server(http, url, args.persistente)

    print(f"Carregando o reconhecimento local ('{args.modelo}'; na primeira vez baixa o modelo)...")
    transcribe = make_transcriber(load_whisper(args.modelo, args.gpu))

    while True:
        try:
            listen_forever(http, transcribe, args)
            return
        except KeyboardInterrupt:
            print("\nAté mais!")
            return
        except Exception as error:  # noqa: BLE001 - microfone desligado, placa de som trocada etc.
            if not args.persistente:
                raise
            print(f"  ⚠️  parou: {error}. Tentando de novo em {RETRY_SECONDS} s.")
            time.sleep(RETRY_SECONDS)


if __name__ == "__main__":
    main()
