"""Testes do biony_ativacao.py (sem microfone, sem Whisper): rode com `python -m pytest clients/pc`."""

from __future__ import annotations

import numpy as np
import pytest

import biony_ativacao as ativ

BLOCK = ativ.BLOCK
SECOND = ativ.RATE // BLOCK  # blocos por segundo


def silence(seconds: float, level: int = 20) -> list[np.ndarray]:
    rng = np.random.default_rng(0)
    return [rng.integers(-level, level, BLOCK).astype(np.int16) for _ in range(int(seconds * SECOND))]


def speech(seconds: float, amplitude: int = 6000) -> list[np.ndarray]:
    blocks = []
    for n in range(int(seconds * SECOND)):
        t = (np.arange(BLOCK) + n * BLOCK) / ativ.RATE
        blocks.append((np.sin(2 * np.pi * 300 * t) * amplitude).astype(np.int16))
    return blocks


class ListSource:
    def __init__(self, blocks: list[np.ndarray]) -> None:
        self._blocks = iter(blocks)

    def read(self):
        try:
            return next(self._blocks)
        except StopIteration:
            raise EOFError from None


def utterances(blocks: list[np.ndarray], detector=None) -> list[np.ndarray]:
    detector = detector or ativ.UtteranceDetector()
    found = [audio for block in blocks if (audio := detector.feed(block)) is not None]
    return found


# ------------------------------------------------------------------ palavra de ativação


@pytest.mark.parametrize(
    "text, heard, command",
    [
        ("Biony, liga a luz", True, "liga a luz"),
        ("Bione liga a luz do quarto", True, "liga a luz do quarto"),
        ("Bioni, que horas são?", True, "que horas são"),
        ("Biôni", True, ""),
        ("ei Biony", True, ""),
        ("oi, Biony, que horas são", True, "que horas são"),
        ("boa noite, Biony", True, "boa noite"),  # o que veio antes do nome também é comando
        ("bio ni liga o ar", True, "liga o ar"),  # o Whisper separou o nome em dois
        ("Biony", True, ""),
        ("bom dia pessoal vamos almoçar", False, "bom dia pessoal vamos almoçar"),
        ("binomial de newton", False, "binomial de newton"),
        ("o biônico é muito forte", False, "o biônico é muito forte"),
        ("hoje o jantar foi bom, falei com o Biony", False, "hoje o jantar foi bom, falei com o Biony"),  # nome longe do começo
        ("", False, ""),
    ],
)
def test_split_wake(text, heard, command):
    assert ativ.split_wake(text) == (heard, command)


def test_has_command():
    assert ativ.has_command("liga a luz")
    assert not ativ.has_command("")
    assert not ativ.has_command(" , ")
    assert not ativ.has_command("é")


# ------------------------------------------------------------------ separar frases


def test_one_phrase_is_cut_at_the_silence():
    found = utterances(silence(1) + speech(1.2) + silence(2))
    assert len(found) == 1
    assert 1.2 < len(found[0]) / ativ.RATE < 2.6  # a fala + o começo guardado + o silêncio final


def test_two_phrases_are_separated():
    assert len(utterances(silence(1) + speech(1) + silence(1.5) + speech(1) + silence(1.5))) == 2


def test_short_pause_inside_a_phrase_does_not_cut_it():
    assert len(utterances(silence(1) + speech(1) + silence(0.5) + speech(1) + silence(2))) == 1


def test_click_is_not_speech():
    assert utterances(silence(1) + speech(0.1) + silence(3)) == []


def test_quiet_room_ignores_low_noise():
    assert utterances(silence(5, level=60)) == []


def test_air_conditioner_noise_is_learned_by_calibration():
    ambient = silence(10, level=900)  # ruído constante (rms ~0,016)
    detector = ativ.UtteranceDetector()
    detector.calibrate(ListSource(ambient[: SECOND]))
    assert detector.noise > 0.008
    # Só o ambiente: nenhuma frase. Com fala por cima: uma frase.
    assert utterances(ambient, detector) == []
    detector = ativ.UtteranceDetector()
    detector.calibrate(ListSource(ambient[: SECOND]))
    noisy_speech = [a + s for a, s in zip(silence(4, level=900), speech(4, amplitude=6000))]
    found = utterances(silence(1, level=900) + noisy_speech + silence(2, level=900), detector)
    assert len(found) == 1


def test_constant_loud_noise_is_not_stuck_forever():
    detector = ativ.UtteranceDetector()
    loud = silence(40, level=2500)  # música alta sem calibração
    first = utterances(loud, detector)
    assert len(first) >= 1  # a primeira vez vira uma "frase" de 15 s (descartada depois pela transcrição)...
    assert detector.noise > 0.02  # ...mas o detector aprendeu o limite e para de se enganar


# ------------------------------------------------------------------ o laço principal


class Script:
    """Monta o que o microfone ouve e o que o Whisper local diria de cada frase, na ordem."""

    def __init__(self, parts: list[tuple[str, str | float]]) -> None:
        # ("fala", "texto que o Whisper entende") ou ("silencio", segundos)
        self.blocks: list[np.ndarray] = silence(1)
        self.texts: list[str] = []
        for kind, value in parts:
            if kind == "fala":
                self.blocks += speech(1.0) + silence(1.0)
                self.texts.append(value)
            else:
                self.blocks += silence(value)
        self.blocks += silence(1)
        self.sent: list[int] = []
        self.events: list[str] = []

    def run(self, wait: float = 3.0) -> None:
        texts = iter(self.texts)
        detector = ativ.UtteranceDetector()
        ativ.run(
            ListSource(self.blocks),
            detector,
            transcribe=lambda audio: next(texts, ""),
            send=lambda audio: self.sent.append(len(audio)) or self.events.append("enviou"),
            beep=lambda: self.events.append("beep"),
            say=lambda text: None,
            wait=wait,
        )


def test_phrase_without_the_name_is_ignored_and_never_sent():
    script = Script([("fala", "bom dia pessoal vamos almoçar"), ("silencio", 2), ("fala", "que horas são")])
    script.run()
    assert script.sent == [] and script.events == []


def test_name_plus_command_sends_that_same_audio():
    script = Script([("fala", "Biony, liga a luz")])
    script.run()
    assert script.events == ["enviou"]


def test_name_alone_beeps_then_sends_the_next_phrase_without_the_name():
    script = Script([("fala", "Biony"), ("fala", "liga o ar"), ("fala", "e apaga a fita")])
    script.run()
    assert script.events == ["beep", "enviou", "enviou"]  # a conversa continua sem repetir o nome


def test_conversation_ends_after_the_wait_and_needs_the_name_again():
    script = Script([
        ("fala", "Biony, liga a luz"),
        ("silencio", 5),               # passou a espera de 3 s: voltou a esperar o nome
        ("fala", "apaga a luz"),       # sem o nome: ignorada
        ("fala", "Biony, apaga a luz"),
    ])
    script.run(wait=3.0)
    assert script.events == ["enviou", "enviou"]
    assert len(script.sent) == 2


def test_name_alone_then_silence_gives_up():
    script = Script([("fala", "Biony"), ("silencio", 6), ("fala", "liga a luz")])
    script.run(wait=3.0)
    assert script.events == ["beep"]  # a fala depois da desistência não tem o nome: ignorada


# ------------------------------------------------------------------ fila de áudio


def test_block_queue_drops_only_the_beep_and_keeps_the_speech_that_was_waiting():
    queue = ativ.BlockQueue()
    waiting = [np.full(BLOCK, i, dtype=np.int16) for i in range(1, 4)]   # fala que chegou durante o reconhecimento
    for block in waiting:
        queue.put(block)
    mark = queue.mark()
    for i in range(10, 20):                                               # o que o microfone ouviu do bipe
        queue.put(np.full(BLOCK, i, dtype=np.int16))
    queue.drop_after(mark, 12)  # pede mais do que há: não pode comer a fala que estava antes
    assert queue.mark() == 3
    assert [int(queue.get(0.01)[0]) for _ in range(3)] == [1, 2, 3]
    assert queue.get(0.01) is None


def test_block_queue_clear():
    queue = ativ.BlockQueue()
    queue.put(np.zeros(BLOCK, dtype=np.int16))
    queue.clear()
    assert queue.get(0.01) is None


# ------------------------------------------------------------------ segundo plano


def test_only_one_instance_can_run(monkeypatch):
    monkeypatch.setattr(ativ, "INSTANCE_PORT", 47899)
    first = ativ.acquire_single_instance()
    assert first is not None
    assert ativ.acquire_single_instance() is None  # a segunda cópia é recusada
    first.close()
    again = ativ.acquire_single_instance()  # soltou a trava: pode rodar de novo
    assert again is not None
    again.close()


def test_log_file_stamps_each_line_and_does_not_grow_forever(tmp_path):
    path = tmp_path / "ativacao.log"
    log = ativ.LogFile(path)
    log.write("primeira")
    log.write(" linha\nsegunda\n")
    log.flush()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0].endswith("primeira linha") and lines[1].endswith("segunda")
    assert lines[0][2] == "/" and lines[0][8] == ":"  # "31/10 17:45:02  ..."

    path.write_text("x" * (ativ.LOG_LIMIT_BYTES + 1), encoding="utf-8")
    ativ.LogFile(path)
    assert path.read_text(encoding="utf-8") == ""


def test_wait_for_server_gives_up_unless_persistent(monkeypatch):
    import httpx

    class Down:
        calls = 0

        def get(self, path):
            Down.calls += 1
            if Down.calls >= 3 and persistent_flag["on"]:
                return httpx.Response(200, request=httpx.Request("GET", "http://x/health"))
            raise httpx.ConnectError("sem rede")

    persistent_flag = {"on": False}
    with pytest.raises(SystemExit):
        ativ.wait_for_server(Down(), "http://x", persistent=False)
    assert Down.calls == 1

    monkeypatch.setattr(ativ.time, "sleep", lambda s: None)
    Down.calls = 0
    persistent_flag["on"] = True
    ativ.wait_for_server(Down(), "http://x", persistent=True)  # tenta de novo até o servidor aparecer
    assert Down.calls == 3
