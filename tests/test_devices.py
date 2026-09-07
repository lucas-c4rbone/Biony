import unittest

from core.biony_core import BionyCore
from core.conversation import ConversationService
from core.devices import DeviceCommand, DeviceManager
from core.events import EventDispatcher
from core.memory import InMemoryMemoryStore
from core.models import CoreEvent, Device, DeviceKind
from core.permissions import SimplePermissionPolicy
from core.simulated_brain import SimulatedBrain
from core.state_machine import StateMachine
from core.tools import ToolCatalog


class FakeBionyDevice:
    """Simula um dispositivo Biony em testes para validar o gerenciador."""

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


class DeviceManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = EventDispatcher()
        self.received_events: list[CoreEvent] = []
        self.events.subscribe(self.received_events.append)
        self.manager = DeviceManager(event_publisher=self.events)
        self.device = Device(
            identifier="biony-1",
            kind=DeviceKind.BIONY,
            capabilities=frozenset({"display", "audio"}),
        )

    def test_register_device(self) -> None:
        self.manager.register_device(self.device)

        self.assertEqual(self.manager.get_device("biony-1"), self.device)
        self.assertIn("device_registered", [event.event_type for event in self.received_events])

    def test_reject_duplicate_id(self) -> None:
        self.manager.register_device(self.device)

        with self.assertRaises(ValueError):
            self.manager.register_device(self.device)

    def test_query_device(self) -> None:
        self.manager.register_device(self.device)

        self.assertEqual(self.manager.get_device("biony-1"), self.device)
        self.assertIsNone(self.manager.get_device("non-existent"))
        self.assertEqual(self.manager.list_devices(), [self.device])

    def test_connect_device(self) -> None:
        self.manager.register_device(self.device)
        connection = FakeBionyDevice()

        self.manager.connect("biony-1", connection)

        dev = self.manager.get_device("biony-1")
        self.assertIsNotNone(dev)
        self.assertTrue(dev.is_available)
        self.assertIsNotNone(dev.last_seen)
        self.assertIn("device_connected", [event.event_type for event in self.received_events])

    def test_disconnect_device(self) -> None:
        self.manager.register_device(self.device)
        connection = FakeBionyDevice()
        self.manager.connect("biony-1", connection)

        self.manager.disconnect("biony-1")

        dev = self.manager.get_device("biony-1")
        self.assertIsNotNone(dev)
        self.assertFalse(dev.is_available)
        self.assertTrue(connection.is_closed)
        self.assertIn("device_disconnected", [event.event_type for event in self.received_events])

    def test_remove_device(self) -> None:
        self.manager.register_device(self.device)

        removed = self.manager.remove_device("biony-1")

        self.assertTrue(removed)
        self.assertIsNone(self.manager.get_device("biony-1"))
        self.assertEqual(self.manager.list_devices(), [])
        self.assertIn("device_removed", [event.event_type for event in self.received_events])

    def test_publish_lifecycle_events(self) -> None:
        self.manager.register_device(self.device)
        self.manager.connect("biony-1")
        self.manager.disconnect("biony-1")
        self.manager.remove_device("biony-1")

        event_types = [event.event_type for event in self.received_events]
        self.assertEqual(
            event_types,
            ["device_registered", "device_connected", "device_disconnected", "device_removed"],
        )

    def test_send_command_to_online_device(self) -> None:
        self.manager.register_device(self.device)
        fake_conn = FakeBionyDevice()
        self.manager.connect("biony-1", fake_conn)

        cmd = self.manager.send_command("biony-1", "play_expression", {"expression": "HAPPY"})

        self.assertEqual(len(fake_conn.received_commands), 1)
        self.assertEqual(fake_conn.received_commands[0], cmd)
        self.assertEqual(self.manager.get_pending_commands("biony-1"), ())
        self.assertIn("command_delivered", [event.event_type for event in self.received_events])

    def test_queue_command_when_offline(self) -> None:
        self.manager.register_device(self.device)

        cmd = self.manager.send_command("biony-1", "play_expression", {"expression": "HAPPY"})

        pending = self.manager.get_pending_commands("biony-1")
        self.assertEqual(pending, (cmd,))
        self.assertIn("command_queued", [event.event_type for event in self.received_events])

    def test_deliver_pending_commands_after_reconnection(self) -> None:
        self.manager.register_device(self.device)
        cmd1 = self.manager.send_command("biony-1", "cmd1")
        cmd2 = self.manager.send_command("biony-1", "cmd2")

        fake_conn = FakeBionyDevice()
        delivered = self.manager.connect("biony-1", fake_conn)

        self.assertEqual(delivered, [cmd1, cmd2])
        self.assertEqual(fake_conn.received_commands, [cmd1, cmd2])
        self.assertEqual(self.manager.get_pending_commands("biony-1"), ())

    def test_preserve_order_of_pending_commands(self) -> None:
        self.manager.register_device(self.device)
        cmd1 = self.manager.send_command("biony-1", "first")
        cmd2 = self.manager.send_command("biony-1", "second")
        cmd3 = self.manager.send_command("biony-1", "third")

        pending = self.manager.get_pending_commands("biony-1")
        self.assertEqual(pending, (cmd1, cmd2, cmd3))

    def test_isolation_between_devices(self) -> None:
        dev2 = Device(identifier="biony-2", kind=DeviceKind.MOBILE_APP)
        self.manager.register_device(self.device)
        self.manager.register_device(dev2)

        cmd1 = self.manager.send_command("biony-1", "cmd_1")
        cmd2 = self.manager.send_command("biony-2", "cmd_2")

        self.assertEqual(self.manager.get_pending_commands("biony-1"), (cmd1,))
        self.assertEqual(self.manager.get_pending_commands("biony-2"), (cmd2,))

    def test_unique_command_ids(self) -> None:
        self.manager.register_device(self.device)
        cmd1 = self.manager.send_command("biony-1", "cmd")
        cmd2 = self.manager.send_command("biony-1", "cmd")

        self.assertNotEqual(cmd1.command_id, cmd2.command_id)

    def test_integration_with_biony_core(self) -> None:
        core = BionyCore(
            state_machine=StateMachine(),
            conversation_service=ConversationService(SimulatedBrain()),
            memory_store=InMemoryMemoryStore(),
            tool_catalog=ToolCatalog(),
            permission_policy=SimplePermissionPolicy(),
            event_publisher=self.events,
            device_manager=self.manager,
        )

        self.assertIs(core.device_manager, self.manager)

    def test_fake_biony_device_receiving_command(self) -> None:
        fake_conn = FakeBionyDevice()
        cmd = DeviceCommand("c1", "biony-1", "set_volume", {"level": 80})

        success = fake_conn.send(cmd)

        self.assertTrue(success)
        self.assertEqual(fake_conn.received_commands, [cmd])
