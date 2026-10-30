import pytest

from biony.core.confirmation import Answer, interpret


@pytest.mark.parametrize("text", ["Sim", "pode sim!", "confirmo", "Manda ver", "claro", "isso mesmo", "ok, pode", "beleza, manda", "pode sim, por favor", "sim, e depois liga a luz do quarto"])
def test_yes(text):
    assert interpret(text) is Answer.YES


@pytest.mark.parametrize("text", ["não", "Nao", "cancela", "deixa pra lá", "sim... não, cancela", "esquece", "esquece isso", "não sei, que horas são?"])
def test_no_wins(text):
    assert interpret(text) is Answer.NO


@pytest.mark.parametrize("text", [
    "que horas são?",
    "liga a luz para mim",
    "",
    # Pedidos novos que contêm palavras de "sim"/"esquece" não podem confirmar nem cancelar à toa.
    "pode me dizer as horas agora?",
    "vai chover amanhã de manhã?",
    "manda uma mensagem pro meu amigo",
    "esquece que eu gosto de luz roxa",
    "pode ligar a luz",
    "vai, liga o ar",
    "deixa a luz azul",
    "isso é muito caro?",
])
def test_unclear(text):
    assert interpret(text) is Answer.UNCLEAR
