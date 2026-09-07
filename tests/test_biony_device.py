import json
import unittest

from core.biony_device import (
    BIONY_1_0_CAPABILITIES,
    VALID_ANIMATIONS,
    VALID_COMMAND_TYPES,
    VALID_EVENT_TYPES,
    VALID_EXPRESSIONS,
    VALID_STATES,
    InvalidCommandError,
    InvalidEventError,
    create_biony_command,
    create_biony_device,
    validate_biony_command,
    validate_biony_event,
)
from core.models import DeviceKind
from core.protocol import (
    PROTOCOL_VERSION,
    CommandMessage,
    EventMessage,
    deserialize_message,
    serialize_message,
)


class BionyDeviceContractTests(unittest.TestCase):
    def test_official_capabilities(self) -> None:
        expected = frozenset({"display", "audio", "microphone", "expressions", "animations", "wifi"})
        self.assertEqual(BIONY_1_0_CAPABILITIES, expected)

        device = create_biony_device("biony-unit-1")
        self.assertEqual(device.kind, DeviceKind.BIONY)
        self.assertEqual(device.capabilities, expected)

    def test_set_state_valid(self) -> None:
        for state in ("BOOTING", "SLEEPING", "IDLE", "WAKING", "LISTENING", "THINKING", "SPEAKING"):
            args = validate_biony_command("set_state", {"state": state})
            self.assertEqual(args["state"], state)

    def test_set_state_invalid(self) -> None:
        with self.assertRaises(InvalidCommandError):
            validate_biony_command("set_state", {"state": "RUNNING"})

        with self.assertRaises(InvalidCommandError):
            validate_biony_command("set_state", {})

        with self.assertRaises(InvalidCommandError):
            validate_biony_command("set_state", {"state": 123})

    def test_set_expression_valid(self) -> None:
        for expr in ("NORMAL", "HAPPY", "CURIOUS", "THINKING", "SURPRISED", "CONFUSED", "SLEEPING", "LISTENING", "SPEAKING", "WAKING"):
            args = validate_biony_command("set_expression", {"expression": expr})
            self.assertEqual(args["expression"], expr)

    def test_set_expression_invalid(self) -> None:
        with self.assertRaises(InvalidCommandError):
            validate_biony_command("set_expression", {"expression": "ROBOTIC"})

        with self.assertRaises(InvalidCommandError):
            validate_biony_command("set_expression", {})

    def test_play_animation_valid(self) -> None:
        animations = [
            "look_left_right", "yawn", "curious", "look_up", "quick_glitch",
            "code_rain", "hammer", "meditation", "gamer_xp", "running",
            "almost_sleeping", "pesqueiro", "octane", "spaghetti_hunter",
        ]
        for anim in animations:
            args = validate_biony_command("play_animation", {"animation": anim})
            self.assertEqual(args["animation"], anim)

    def test_play_animation_invalid(self) -> None:
        with self.assertRaises(InvalidCommandError):
            validate_biony_command("play_animation", {"animation": "breakdance"})

        with self.assertRaises(InvalidCommandError):
            validate_biony_command("play_animation", {})

    def test_speak_valid(self) -> None:
        args = validate_biony_command("speak", {"audio_id": "aud_001", "interruptible": True})
        self.assertEqual(args["audio_id"], "aud_001")
        self.assertTrue(args["interruptible"])

        # Default interruptible
        args_default = validate_biony_command("speak", {"audio_id": "aud_002"})
        self.assertTrue(args_default["interruptible"])

    def test_stop_speaking(self) -> None:
        args = validate_biony_command("stop_speaking", {})
        self.assertEqual(args, {})

        args_none = validate_biony_command("stop_speaking", None)
        self.assertEqual(args_none, {})

    def test_set_volume_valid(self) -> None:
        for vol in (0, 50, 100, 75.5):
            args = validate_biony_command("set_volume", {"volume": vol})
            self.assertEqual(args["volume"], vol)

    def test_set_volume_below_zero(self) -> None:
        with self.assertRaises(InvalidCommandError):
            validate_biony_command("set_volume", {"volume": -1})

        with self.assertRaises(InvalidCommandError):
            validate_biony_command("set_volume", {"volume": -0.5})

    def test_set_volume_above_100(self) -> None:
        with self.assertRaises(InvalidCommandError):
            validate_biony_command("set_volume", {"volume": 101})

        with self.assertRaises(InvalidCommandError):
            validate_biony_command("set_volume", {"volume": 100.1})

    def test_wake_detected(self) -> None:
        evt_data = validate_biony_event("wake_detected", {"confidence": 0.95})
        self.assertEqual(evt_data["confidence"], 0.95)

    def test_button_pressed(self) -> None:
        evt_data = validate_biony_event("button_pressed", {"button_id": "main"})
        self.assertEqual(evt_data["button_id"], "main")

    def test_audio_started(self) -> None:
        evt_data = validate_biony_event("audio_started", {"audio_id": "aud_001"})
        self.assertEqual(evt_data["audio_id"], "aud_001")

    def test_audio_finished(self) -> None:
        evt_data = validate_biony_event("audio_finished", {"audio_id": "aud_001"})
        self.assertEqual(evt_data["audio_id"], "aud_001")

    def test_animation_finished(self) -> None:
        evt_data = validate_biony_event("animation_finished", {"animation": "yawn"})
        self.assertEqual(evt_data["animation"], "yawn")

    def test_device_error(self) -> None:
        evt_data = validate_biony_event("device_error", {"code": "WIFI_FAIL", "message": "Connection lost"})
        self.assertEqual(evt_data["code"], "WIFI_FAIL")

    def test_command_serialization(self) -> None:
        cmd_args = validate_biony_command("set_expression", {"expression": "HAPPY"})
        cmd_msg = CommandMessage(
            command_id="cmd-biony-1",
            command_type="set_expression",
            arguments=cmd_args,
        )

        serialized = serialize_message(cmd_msg)
        parsed = json.loads(serialized)
        self.assertEqual(parsed["type"], "COMMAND")
        self.assertEqual(parsed["command_type"], "set_expression")
        self.assertEqual(parsed["arguments"]["expression"], "HAPPY")

        deserialized = deserialize_message(serialized)
        self.assertIsInstance(deserialized, CommandMessage)
        self.assertEqual(deserialized.command_id, "cmd-biony-1")
        self.assertEqual(deserialized.command_type, "set_expression")
        self.assertEqual(deserialized.arguments["expression"], "HAPPY")

    def test_event_serialization(self) -> None:
        evt_data = validate_biony_event("wake_detected", {"keyword": "Biony"})
        evt_msg = EventMessage(
            event_id="evt-biony-1",
            event_type="wake_detected",
            data=evt_data,
            timestamp=1725624000.0,
        )

        serialized = serialize_message(evt_msg)
        parsed = json.loads(serialized)
        self.assertEqual(parsed["type"], "EVENT")
        self.assertEqual(parsed["event_type"], "wake_detected")
        self.assertEqual(parsed["data"]["keyword"], "Biony")

        deserialized = deserialize_message(serialized)
        self.assertIsInstance(deserialized, EventMessage)
        self.assertEqual(deserialized.event_id, "evt-biony-1")
        self.assertEqual(deserialized.event_type, "wake_detected")

    def test_protocol_v1_integration(self) -> None:
        cmd = create_biony_command("biony-1", "play_animation", {"animation": "code_rain"})
        cmd_msg = CommandMessage(
            command_id=cmd.command_id,
            command_type=cmd.command_type,
            arguments=cmd.arguments,
        )

        serialized = serialize_message(cmd_msg)
        parsed = json.loads(serialized)

        self.assertEqual(parsed["protocol_version"], PROTOCOL_VERSION)
        self.assertEqual(parsed["protocol_version"], "1.0")
        self.assertEqual(parsed["command_type"], "play_animation")
        self.assertEqual(parsed["arguments"]["animation"], "code_rain")
