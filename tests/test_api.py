from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from core.api import LocalDeviceAuthenticator, create_app
from core.biony_core import BionyCore
from core.conversation import ConversationService
from core.events import EventDispatcher
from core.memory import InMemoryMemoryStore
from core.permissions import SimplePermissionPolicy
from core.simulated_brain import SimulatedBrain
from core.state_machine import BionyState, StateMachine
from core.tools import ToolCatalog


class FailingBrain:
    def respond(self, message: str) -> str:
        raise RuntimeError("internal failure")


class LocalApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = self._create_core()
        self.client = TestClient(
            create_app(self.core, LocalDeviceAuthenticator("local-test-credential"))
        )
        self._register_device()

    def test_health_endpoint_reports_core_status(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "state": "IDLE"})

    def test_authenticated_device_can_send_messages_and_preserve_session(self) -> None:
        first = self._message("Olá, Biony")
        session_id = first.json()["session_id"]
        second = self._message("Qual seu nome?", session_id)

        self.assertEqual(first.status_code, 200)
        self.assertIn("Lucas", first.json()["message"])
        self.assertEqual(second.json()["session_id"], session_id)
        self.assertIn("Biony", second.json()["message"])

    def test_rejects_invalid_or_unregistered_devices(self) -> None:
        invalid = self.client.post(
            "/devices/register", json={"device_id": "invalid", "credential": "wrong"}
        )
        unregistered = self.client.post(
            "/messages",
            json={"device_id": "unknown", "credential": "local-test-credential", "message": "Olá"},
        )

        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(unregistered.status_code, 401)

    def test_authenticated_websocket_receives_core_events(self) -> None:
        with self.client.websocket_connect(
            "/ws?device_id=desktop&credential=local-test-credential"
        ) as websocket:
            self.core.transition_to(BionyState.LISTENING)

            event = websocket.receive_json()

        self.assertEqual(event, {"event_type": "state_changed", "data": {"state": "LISTENING"}})

    def test_websocket_rejects_invalid_credential(self) -> None:
        with self.assertRaises(Exception):
            with self.client.websocket_connect("/ws?device_id=desktop&credential=wrong"):
                pass

    def test_session_endpoint_returns_only_its_session_context(self) -> None:
        first_session = self._message("Olá", "first").json()["session_id"]
        self._message("Qual seu nome?", "second")

        response = self.client.get(
            f"/sessions/{first_session}",
            params={"device_id": "desktop", "credential": "local-test-credential"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["messages"][0]["content"], "Olá")
        self.assertEqual(len(response.json()["messages"]), 2)

    def test_internal_core_errors_are_sanitized(self) -> None:
        client = TestClient(
            create_app(self._create_core(FailingBrain()), LocalDeviceAuthenticator("local-test-credential"))
        )
        client.post("/devices/register", json={"device_id": "desktop", "credential": "local-test-credential"})

        response = client.post(
            "/messages",
            json={"device_id": "desktop", "credential": "local-test-credential", "message": "Olá"},
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Unable to process message.")
        self.assertNotIn("internal failure", response.text)

    def test_api_does_not_access_tools_or_memory_stores_directly(self) -> None:
        source = Path("core/api/service.py").read_text(encoding="utf-8")

        self.assertNotIn("ToolCatalog", source)
        self.assertNotIn("MemoryStore", source)

    def _register_device(self) -> None:
        response = self.client.post(
            "/devices/register",
            json={"device_id": "desktop", "credential": "local-test-credential"},
        )
        self.assertEqual(response.status_code, 204)

    def _message(self, message: str, session_id: str | None = None):
        return self.client.post(
            "/messages",
            json={
                "device_id": "desktop",
                "credential": "local-test-credential",
                "message": message,
                "session_id": session_id,
            },
        )

    @staticmethod
    def _create_core(brain: object | None = None) -> BionyCore:
        return BionyCore(
            state_machine=StateMachine(),
            conversation_service=ConversationService(brain or SimulatedBrain()),
            memory_store=InMemoryMemoryStore(),
            tool_catalog=ToolCatalog(),
            permission_policy=SimplePermissionPolicy(),
            event_publisher=EventDispatcher(),
        )