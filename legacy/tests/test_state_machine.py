import unittest

from core import BionyState, StateMachine
from core.simulated_brain import SimulatedBrain
from face import FaceExpression


class StateMachineTests(unittest.TestCase):
    def test_notifies_listeners_on_change(self) -> None:
        received: list[BionyState] = []
        machine = StateMachine()
        machine.subscribe(received.append)

        self.assertEqual(received, [BionyState.IDLE])
        self.assertTrue(machine.transition_to(BionyState.LISTENING))
        self.assertEqual(received, [BionyState.IDLE, BionyState.LISTENING])
        self.assertFalse(machine.transition_to(BionyState.LISTENING))


class SimulatedBrainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.brain = SimulatedBrain()

    def test_recognizes_greeting_with_accents(self) -> None:
        self.assertIn("Lucas", self.brain.respond("Olá, Biony"))

    def test_informs_its_name(self) -> None:
        self.assertIn("Biony", self.brain.respond("Qual seu nome?"))

    def test_handles_unknown_message(self) -> None:
        self.assertIn("cérebro real", self.brain.respond("Me conte uma curiosidade"))


class FaceExpressionTests(unittest.TestCase):
    def test_visual_vocabulary_contains_requested_expressions(self) -> None:
        expected = {"NORMAL", "HAPPY", "CURIOUS", "THINKING", "SURPRISED", "CONFUSED", "SLEEPING", "LISTENING", "SPEAKING"}
        self.assertTrue(expected.issubset({expression.name for expression in FaceExpression}))
