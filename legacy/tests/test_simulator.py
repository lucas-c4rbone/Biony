import unittest

from app.simulator import SimulatorModel, create_brain
from core.models import BrainResponse, ToolRequest, ToolResult
from core.tools import ToolDefinition
from face.expressions import FaceExpression


class ConfirmationBrain:
    def respond(self, message: str) -> str:
        return "unused"

    def respond_with_tools(self, message: str) -> BrainResponse:
        return BrainResponse(tool_requests=(ToolRequest("shutdown_computer"),))

    def respond_to_tool_result(self, result: ToolResult) -> BrainResponse:
        return BrainResponse(message="Ferramenta confirmada.")


class ConfirmationTool:
    definition = ToolDefinition(
        name="shutdown_computer",
        description="Desliga o computador.",
        requires_confirmation=True,
    )

    def execute(self, request: ToolRequest) -> ToolResult:
        return ToolResult(request.name, True, "desligado", request.identifier)


class SimulatorModelTests(unittest.TestCase):
    def test_default_mode_uses_simulated_brain_without_api_key(self) -> None:
        model = SimulatorModel()

        self.assertEqual(model.brain_name, "SimulatedBrain")
        response = model.handle_message("Biony, oi")

        self.assertIn("Lucas", response.message or "")
        self.assertEqual(model.snapshot.state.name, "IDLE")
        self.assertIn("state_changed", model.snapshot.events)
        self.assertIn("response_produced", model.snapshot.events)
        self.assertEqual(model.device.state, "IDLE")

    def test_manual_expression_and_animation_use_device_contract(self) -> None:
        model = SimulatorModel()

        model.set_expression(FaceExpression.SURPRISED)
        model.play_animation("code_rain")

        self.assertEqual(model.device.expression, "SURPRISED")
        self.assertEqual(model.device.animations, ["code_rain"])
        self.assertEqual(model.snapshot.animation, "code_rain")

    def test_memory_uses_core_memory_store(self) -> None:
        model = SimulatorModel()

        model.handle_message("guarda que minha impressora favorita e a Kobra 4.")

        self.assertEqual(
            model.handle_message("qual e minha impressora favorita?").message,
            "Lembro: minha impressora favorita e a Kobra 4.",
        )

    def test_confirmation_is_exposed_from_core(self) -> None:
        model = SimulatorModel(ConfirmationBrain())
        model.core.tool_catalog.register(ConfirmationTool())

        model.handle_message("Desligue o computador")

        action_id = model.snapshot.pending_action_id
        self.assertIsNotNone(action_id)
        model.confirm_pending_action(action_id or "", "sim")
        self.assertIsNone(model.snapshot.pending_action_id)
        self.assertEqual(model.snapshot.response, "Ferramenta confirmada.")

    def test_brain_factory_keeps_all_modes(self) -> None:
        self.assertEqual(type(create_brain("simulated")).__name__, "SimulatedBrain")
        self.assertEqual(type(create_brain("openai")).__name__, "OpenAIBrain")
        self.assertEqual(type(create_brain("openrouter")).__name__, "OpenRouterBrain")
        self.assertEqual(type(create_brain("real")).__name__, "RealBrain")


if __name__ == "__main__":
    unittest.main()
