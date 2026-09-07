import json
import unittest

from core.api.service import LocalDeviceAuthenticator
from core.devices import DeviceCommand, DeviceManager
from core.events import EventDispatcher
from core.models import CoreEvent, DeviceKind
from core.protocol import (
    CommandAckMessage,
    CommandMessage,
    DeviceProtocolHandler,
    ErrorMessage,
    EventMessage,
    HeartbeatAckMessage,
    HeartbeatMessage,
    HelloAckMessage,
    HelloMessage,
    InvalidProtocolVersionError,
    ProtocolDeviceConnection,
    ProtocolError,
    deserialize_message,
    serialize_message,
)


class FakeTransport:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.sent_messages: list[str] = []
        self.is_closed = False

    def send_text(self, text: str) -> bool:
        if self.should_fail:
            return False
        self.sent_messages.append(text)
        return True

    def close(self) -> None:
        self.is_closed = True


class ProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = EventDispatcher()
        self.received_events: list[CoreEvent] = []
        self.events.subscribe(self.received_events.append)
        self.device_manager = DeviceManager(event_publisher=self.events)
        self.authenticator = LocalDeviceAuthenticator("secret-cred")
        self.handler = DeviceProtocolHandler(
            device_manager=self.device_manager,
            authenticator=self.authenticator,
        )

    def test_serialization_hello(self) -> None:
        msg = HelloMessage(
            device_id="biony-1",
            device_kind="BIONY",
            capabilities=("display", "audio"),
            credential="secret-cred",
        )
        json_str = serialize_message(msg)
        parsed = json.loads(json_str)

        self.assertEqual(parsed["type"], "HELLO")
        self.assertEqual(parsed["protocol_version"], "1.0")
        self.assertEqual(parsed["device_id"], "biony-1")
        self.assertEqual(parsed["device_kind"], "BIONY")
        self.assertEqual(parsed["capabilities"], ["display", "audio"])
        self.assertEqual(parsed["credential"], "secret-cred")

    def test_deserialization_hello(self) -> None:
        raw = json.dumps({
            "type": "HELLO",
            "protocol_version": "1.0",
            "device_id": "biony-1",
            "device_kind": "BIONY",
            "capabilities": ["display"],
            "credential": "secret-cred",
        })
        msg = deserialize_message(raw)

        self.assertIsInstance(msg, HelloMessage)
        self.assertEqual(msg.device_id, "biony-1")
        self.assertEqual(msg.device_kind, "BIONY")
        self.assertEqual(msg.capabilities, ("display",))
        self.assertEqual(msg.credential, "secret-cred")

    def test_hello_valid(self) -> None:
        raw = json.dumps({
            "type": "HELLO",
            "protocol_version": "1.0",
            "device_id": "biony-1",
            "device_kind": "BIONY",
            "capabilities": ["display"],
            "credential": "secret-cred",
        })
        transport = FakeTransport()
        response, device_id = self.handler.handle_raw_message(raw, transport)

        self.assertEqual(device_id, "biony-1")
        self.assertIsInstance(response, HelloAckMessage)
        self.assertTrue(response.accepted)
        self.assertIsNotNone(self.device_manager.get_device("biony-1"))
        self.assertTrue(self.device_manager.get_device("biony-1").is_available)

    def test_hello_invalid(self) -> None:
        raw = json.dumps({
            "type": "HELLO",
            "protocol_version": "1.0",
            # missing required device_id
        })
        transport = FakeTransport()
        response, device_id = self.handler.handle_raw_message(raw, transport)

        self.assertIsInstance(response, ErrorMessage)
        self.assertEqual(response.code, "INVALID_MESSAGE")

    def test_version_incompatible(self) -> None:
        raw = json.dumps({
            "type": "HELLO",
            "protocol_version": "2.0",
            "device_id": "biony-1",
            "device_kind": "BIONY",
            "capabilities": [],
            "credential": "secret-cred",
        })
        transport = FakeTransport()

        with self.assertRaises(InvalidProtocolVersionError):
            deserialize_message(raw)

        response, _ = self.handler.handle_raw_message(raw, transport)
        self.assertIsInstance(response, HelloAckMessage)
        self.assertFalse(response.accepted)
        self.assertIn("Incompatible protocol version", response.error)

    def test_auth_valid(self) -> None:
        msg = HelloMessage("biony-1", "BIONY", (), "secret-cred")
        transport = FakeTransport()
        resp, dev_id = self.handler.handle_message(msg, transport)

        self.assertIsInstance(resp, HelloAckMessage)
        self.assertTrue(resp.accepted)
        self.assertEqual(dev_id, "biony-1")

    def test_auth_invalid(self) -> None:
        msg = HelloMessage("biony-1", "BIONY", (), "wrong-cred")
        transport = FakeTransport()
        resp, dev_id = self.handler.handle_message(msg, transport)

        self.assertIsInstance(resp, HelloAckMessage)
        self.assertFalse(resp.accepted)
        self.assertEqual(resp.error, "Invalid device credential.")
        self.assertIsNone(dev_id)

    def test_hello_ack_accepted(self) -> None:
        msg = HelloAckMessage(accepted=True, server_info="Biony 1.0")
        json_str = serialize_message(msg)
        deserialized = deserialize_message(json_str)

        self.assertIsInstance(deserialized, HelloAckMessage)
        self.assertTrue(deserialized.accepted)
        self.assertEqual(deserialized.server_info, "Biony 1.0")

    def test_hello_ack_rejected(self) -> None:
        msg = HelloAckMessage(accepted=False, error="Bad credentials")
        json_str = serialize_message(msg)
        deserialized = deserialize_message(json_str)

        self.assertIsInstance(deserialized, HelloAckMessage)
        self.assertFalse(deserialized.accepted)
        self.assertEqual(deserialized.error, "Bad credentials")

    def test_heartbeat(self) -> None:
        msg = HeartbeatMessage(timestamp=12345.67)
        json_str = serialize_message(msg)
        deserialized = deserialize_message(json_str)

        self.assertIsInstance(deserialized, HeartbeatMessage)
        self.assertEqual(deserialized.timestamp, 12345.67)

    def test_heartbeat_ack(self) -> None:
        hello = HelloMessage("biony-1", "BIONY", (), "secret-cred")
        transport = FakeTransport()
        self.handler.handle_message(hello, transport)

        hb = HeartbeatMessage(timestamp=999.0)
        resp, dev_id = self.handler.handle_message(hb, transport, current_device_id="biony-1")

        self.assertIsInstance(resp, HeartbeatAckMessage)
        self.assertEqual(resp.timestamp, 999.0)
        self.assertIsNotNone(self.device_manager.get_device("biony-1").last_seen)

    def test_command(self) -> None:
        cmd = CommandMessage("c-100", "set_volume", {"level": 50})
        json_str = serialize_message(cmd)
        parsed = deserialize_message(json_str)

        self.assertIsInstance(parsed, CommandMessage)
        self.assertEqual(parsed.command_id, "c-100")
        self.assertEqual(parsed.command_type, "set_volume")
        self.assertEqual(parsed.arguments, {"level": 50})

    def test_command_ack(self) -> None:
        hello = HelloMessage("biony-1", "BIONY", (), "secret-cred")
        transport = FakeTransport()
        self.handler.handle_message(hello, transport)

        ack = CommandAckMessage("c-100", accepted=True)
        resp, _ = self.handler.handle_message(ack, transport, current_device_id="biony-1")

        self.assertIsNone(resp)
        events = [e.event_type for e in self.received_events if e.event_type == "command_acknowledged"]
        self.assertEqual(len(events), 1)

    def test_event(self) -> None:
        evt = EventMessage("e-1", "button_click", {"button": "wake"}, timestamp=500.0)
        transport = FakeTransport()
        resp, _ = self.handler.handle_message(evt, transport, current_device_id="biony-1")

        self.assertIsNone(resp)
        events = [e for e in self.received_events if e.event_type == "device_event"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].data["event_id"], "e-1")
        self.assertEqual(events[0].data["event_type"], "button_click")

    def test_error(self) -> None:
        err = ErrorMessage("ERR_SYSTEM", "System halted")
        transport = FakeTransport()
        resp, _ = self.handler.handle_message(err, transport, current_device_id="biony-1")

        self.assertIsNone(resp)
        events = [e for e in self.received_events if e.event_type == "device_error"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].data["code"], "ERR_SYSTEM")

    def test_command_with_arguments(self) -> None:
        cmd = CommandMessage(
            command_id="cmd-88",
            command_type="play_animation",
            arguments={"name": "blink", "repeat": 3, "speed": 1.5},
        )
        json_str = serialize_message(cmd)
        deserialized = deserialize_message(json_str)

        self.assertIsInstance(deserialized, CommandMessage)
        self.assertEqual(deserialized.arguments["name"], "blink")
        self.assertEqual(deserialized.arguments["repeat"], 3)
        self.assertEqual(deserialized.arguments["speed"], 1.5)

    def test_command_id_preserved(self) -> None:
        hello = HelloMessage("biony-1", "BIONY", (), "secret-cred")
        transport = FakeTransport()
        self.handler.handle_message(hello, transport)

        dev_cmd = self.device_manager.send_command("biony-1", "test_cmd", {"a": 1})
        sent_json = transport.sent_messages[0]
        parsed = deserialize_message(sent_json)

        self.assertIsInstance(parsed, CommandMessage)
        self.assertEqual(parsed.command_id, dev_cmd.command_id)

    def test_event_id_preserved(self) -> None:
        evt = EventMessage("evt-unique-123", "sensor_read", {"temp": 25.0})
        transport = FakeTransport()
        self.handler.handle_message(evt, transport, current_device_id="biony-1")

        events = [e for e in self.received_events if e.event_type == "device_event"]
        self.assertEqual(events[0].data["event_id"], "evt-unique-123")

    def test_device_reconnecting(self) -> None:
        hello1 = HelloMessage("biony-1", "BIONY", (), "secret-cred")
        transport1 = FakeTransport()
        self.handler.handle_message(hello1, transport1)

        self.device_manager.disconnect("biony-1")
        self.assertFalse(self.device_manager.get_device("biony-1").is_available)

        hello2 = HelloMessage("biony-1", "BIONY", (), "secret-cred")
        transport2 = FakeTransport()
        resp, dev_id = self.handler.handle_message(hello2, transport2)

        self.assertEqual(dev_id, "biony-1")
        self.assertTrue(resp.accepted)
        self.assertTrue(self.device_manager.get_device("biony-1").is_available)

    def test_pending_command_delivered_on_reconnect(self) -> None:
        # Register device first while offline
        hello1 = HelloMessage("biony-1", "BIONY", (), "secret-cred")
        transport1 = FakeTransport()
        self.handler.handle_message(hello1, transport1)
        self.device_manager.disconnect("biony-1")

        # Send command while offline
        cmd = self.device_manager.send_command("biony-1", "offline_task", {"val": 42})
        self.assertEqual(len(self.device_manager.get_pending_commands("biony-1")), 1)

        # Reconnect
        transport2 = FakeTransport()
        hello2 = HelloMessage("biony-1", "BIONY", (), "secret-cred")
        self.handler.handle_message(hello2, transport2)

        self.assertEqual(len(transport2.sent_messages), 1)
        sent_cmd = deserialize_message(transport2.sent_messages[0])
        self.assertIsInstance(sent_cmd, CommandMessage)
        self.assertEqual(sent_cmd.command_id, cmd.command_id)
        self.assertEqual(len(self.device_manager.get_pending_commands("biony-1")), 0)

    def test_malformed_messages(self) -> None:
        transport = FakeTransport()

        # Not valid JSON
        resp, _ = self.handler.handle_raw_message("{not json}", transport)
        self.assertIsInstance(resp, ErrorMessage)
        self.assertEqual(resp.code, "INVALID_MESSAGE")

        # Not a dict
        resp, _ = self.handler.handle_raw_message("[1, 2, 3]", transport)
        self.assertIsInstance(resp, ErrorMessage)
        self.assertEqual(resp.code, "INVALID_MESSAGE")

    def test_unknown_message_types(self) -> None:
        raw = json.dumps({"type": "SUPER_UNKNOWN", "protocol_version": "1.0"})
        transport = FakeTransport()

        resp, _ = self.handler.handle_raw_message(raw, transport)
        self.assertIsInstance(resp, ErrorMessage)
        self.assertEqual(resp.code, "INVALID_MESSAGE")

    def test_fake_device_connection_receiving_commands(self) -> None:
        transport = FakeTransport()
        conn = ProtocolDeviceConnection(transport)
        dev_cmd = DeviceCommand("c-1", "biony-1", "ping", {})

        success = conn.send(dev_cmd)

        self.assertTrue(success)
        self.assertEqual(len(transport.sent_messages), 1)
        parsed = deserialize_message(transport.sent_messages[0])
        self.assertIsInstance(parsed, CommandMessage)
        self.assertEqual(parsed.command_id, "c-1")
