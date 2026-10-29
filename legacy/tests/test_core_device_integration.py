import unittest
from inspect import getsource

from core.biony_core import BionyCore
from core.biony_device import InvalidCommandError, create_biony_device
from core.conversation import ConversationService
from core.devices import DeviceCommand, DeviceManager
from core.events import EventDispatcher
from core.memory import InMemoryMemoryStore
from core.permissions import SimplePermissionPolicy
from core.simulated_brain import SimulatedBrain
from core.state_machine import BionyState, StateMachine
from core.tools import ToolCatalog
from face.expressions import FaceExpression


class FakeBionyDeviceConnection:
    """Simula a conexão de transporte de um dispositivo físico Biony 1.0."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.received_commands: list[DeviceCommand] = []
        self.is_closed = False

    def send(self, command: DeviceCommand) -> bool:
        if self.should_fail:
            return False
        self.received_commands.append(command)
        return True

    def close(self) -> None:
        self.is_closed = True


class CoreDeviceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = EventDispatcher()
        self.device_manager = DeviceManager(event_publisher=self.events)
        self.state_machine = StateMachine(initial_state=BionyState.IDLE)
        self.core = BionyCore(
            state_machine=self.state_machine,
            conversation_service=ConversationService(SimulatedBrain()),
            memory_store=InMemoryMemoryStore(),
            tool_catalog=ToolCatalog(),
            permission_policy=SimplePermissionPolicy(),
            event_publisher=self.events,
            device_manager=self.device_manager,
        )
        self.device1 = create_biony_device("biony-1")
        self.device_manager.register_device(self.device1)

    def test_state_transition_idle_to_waking(self) -> None:
        conn = FakeBionyDeviceConnection()
        self.device_manager.connect("biony-1", conn)

        self.core.transition_to(BionyState.WAKING)

        self.assertEqual(len(conn.received_commands), 1)
        cmd = conn.received_commands[0]
        self.assertEqual(cmd.command_type, "set_state")
        self.assertEqual(cmd.arguments["state"], "WAKING")

    def test_state_transition_waking_to_listening(self) -> None:
        conn = FakeBionyDeviceConnection()
        self.device_manager.connect("biony-1", conn)
        self.core.transition_to(BionyState.WAKING)

        self.core.transition_to(BionyState.LISTENING)

        cmd = conn.received_commands[-1]
        self.assertEqual(cmd.command_type, "set_state")
        self.assertEqual(cmd.arguments["state"], "LISTENING")

    def test_state_transition_listening_to_thinking(self) -> None:
        conn = FakeBionyDeviceConnection()
        self.device_manager.connect("biony-1", conn)
        self.core.transition_to(BionyState.LISTENING)

        self.core.transition_to(BionyState.THINKING)

        cmd = conn.received_commands[-1]
        self.assertEqual(cmd.command_type, "set_state")
        self.assertEqual(cmd.arguments["state"], "THINKING")

    def test_state_transition_thinking_to_speaking(self) -> None:
        conn = FakeBionyDeviceConnection()
        self.device_manager.connect("biony-1", conn)
        self.core.transition_to(BionyState.THINKING)

        self.core.transition_to(BionyState.SPEAKING)

        cmd = conn.received_commands[-1]
        self.assertEqual(cmd.command_type, "set_state")
        self.assertEqual(cmd.arguments["state"], "SPEAKING")

    def test_state_transition_speaking_to_idle(self) -> None:
        conn = FakeBionyDeviceConnection()
        self.device_manager.connect("biony-1", conn)
        self.core.transition_to(BionyState.SPEAKING)

        self.core.transition_to(BionyState.IDLE)

        cmd = conn.received_commands[-1]
        self.assertEqual(cmd.command_type, "set_state")
        self.assertEqual(cmd.arguments["state"], "IDLE")

    def test_state_transition_idle_to_sleeping(self) -> None:
        conn = FakeBionyDeviceConnection()
        self.device_manager.connect("biony-1", conn)

        self.core.transition_to(BionyState.SLEEPING)

        cmd = conn.received_commands[-1]
        self.assertEqual(cmd.command_type, "set_state")
        self.assertEqual(cmd.arguments["state"], "SLEEPING")

    def test_set_expression_sent_correctly(self) -> None:
        conn = FakeBionyDeviceConnection()
        self.device_manager.connect("biony-1", conn)

        cmds = self.core.set_device_expression(FaceExpression.HAPPY)

        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0].command_type, "set_expression")
        self.assertEqual(cmds[0].arguments["expression"], "HAPPY")
        self.assertEqual(conn.received_commands[0], cmds[0])

    def test_play_animation_sent_correctly(self) -> None:
        conn = FakeBionyDeviceConnection()
        self.device_manager.connect("biony-1", conn)

        cmds = self.core.play_device_animation("code_rain")

        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0].command_type, "play_animation")
        self.assertEqual(cmds[0].arguments["animation"], "code_rain")
        self.assertEqual(conn.received_commands[0], cmds[0])

    def test_command_id_preserved(self) -> None:
        conn = FakeBionyDeviceConnection()
        self.device_manager.connect("biony-1", conn)

        cmds = self.core.set_device_expression(FaceExpression.CURIOUS)

        self.assertTrue(cmds[0].command_id)
        self.assertEqual(conn.received_commands[0].command_id, cmds[0].command_id)

    def test_online_device_receives_immediately(self) -> None:
        conn = FakeBionyDeviceConnection()
        self.device_manager.connect("biony-1", conn)

        self.core.transition_to(BionyState.WAKING)

        self.assertEqual(len(conn.received_commands), 1)
        self.assertEqual(self.device_manager.get_pending_commands("biony-1"), ())

    def test_offline_device_receives_command_in_queue(self) -> None:
        cmds = self.core.set_device_expression(FaceExpression.SURPRISED)

        self.assertEqual(len(cmds), 1)
        pending = self.device_manager.get_pending_commands("biony-1")
        self.assertEqual(pending, tuple(cmds))

    def test_reconnection_delivers_queued_commands(self) -> None:
        cmd1 = self.core.set_device_expression(FaceExpression.HAPPY)[0]
        cmd2 = self.core.play_device_animation("yawn")[0]

        conn = FakeBionyDeviceConnection()
        delivered = self.device_manager.connect("biony-1", conn)

        self.assertEqual(delivered, [cmd1, cmd2])
        self.assertEqual(conn.received_commands, [cmd1, cmd2])
        self.assertEqual(self.device_manager.get_pending_commands("biony-1"), ())

    def test_multiple_devices_isolation(self) -> None:
        device2 = create_biony_device("biony-2")
        self.device_manager.register_device(device2)
        conn1 = FakeBionyDeviceConnection()
        self.device_manager.connect("biony-1", conn1)

        cmds = self.core.set_device_expression(FaceExpression.HAPPY, device_id="biony-1")

        self.assertEqual(len(cmds), 1)
        self.assertEqual(len(conn1.received_commands), 1)
        self.assertEqual(self.device_manager.get_pending_commands("biony-2"), ())

    def test_absence_of_device_does_not_break_core(self) -> None:
        core_no_devices = BionyCore(
            state_machine=StateMachine(),
            conversation_service=ConversationService(SimulatedBrain()),
            memory_store=InMemoryMemoryStore(),
            tool_catalog=ToolCatalog(),
            permission_policy=SimplePermissionPolicy(),
            event_publisher=self.events,
            device_manager=None,
        )

        self.assertTrue(core_no_devices.transition_to(BionyState.LISTENING))
        self.assertEqual(core_no_devices.set_device_expression(FaceExpression.HAPPY), [])
        self.assertEqual(core_no_devices.play_device_animation("code_rain"), [])

    def test_no_state_machine_duplication(self) -> None:
        self.assertIs(self.core.state_machine, self.state_machine)
        self.assertFalse(hasattr(self.device_manager, "state_machine"))

    def test_no_direct_device_connection_execution_by_core(self) -> None:
        core_source = getsource(BionyCore)
        self.assertNotIn("DeviceConnection", core_source)
        self.assertNotIn(".send(", core_source)

    def test_validation_centralized_in_biony_device(self) -> None:
        with self.assertRaises(InvalidCommandError):
            self.core.set_device_expression("INVALID_EXPRESSION_NAME")

        with self.assertRaises(InvalidCommandError):
            self.core.play_device_animation("INVALID_ANIMATION_NAME")

        with self.assertRaises(InvalidCommandError):
            self.core.set_device_state("INVALID_STATE_NAME")
