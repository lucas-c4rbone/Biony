import pytest

from biony.core.confirmation import Answer, interpret


@pytest.mark.parametrize("text", ["Sim", "pode sim!", "confirmo", "Manda ver", "claro"])
def test_yes(text):
    assert interpret(text) is Answer.YES


@pytest.mark.parametrize("text", ["não", "Nao", "cancela", "deixa pra lá", "sim... não, cancela"])
def test_no_wins(text):
    assert interpret(text) is Answer.NO


@pytest.mark.parametrize("text", ["que horas são?", "liga a luz para mim", ""])
def test_unclear(text):
    assert interpret(text) is Answer.UNCLEAR
