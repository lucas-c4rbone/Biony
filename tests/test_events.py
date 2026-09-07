import unittest

from core.events import EventDispatcher
from core.models import CoreEvent


class EventDispatcherTests(unittest.TestCase):
    def test_registers_a_listener_and_delivers_an_event(self) -> None:
        dispatcher = EventDispatcher()
        received: list[CoreEvent] = []
        event = CoreEvent(event_type="test_event")

        dispatcher.subscribe(received.append)
        dispatcher.publish(event)

        self.assertEqual(received, [event])

    def test_delivers_events_to_multiple_listeners(self) -> None:
        dispatcher = EventDispatcher()
        first_received: list[CoreEvent] = []
        second_received: list[CoreEvent] = []
        event = CoreEvent(event_type="test_event")

        dispatcher.subscribe(first_received.append)
        dispatcher.subscribe(second_received.append)
        dispatcher.publish(event)

        self.assertEqual(first_received, [event])
        self.assertEqual(second_received, [event])

    def test_removes_a_listener(self) -> None:
        dispatcher = EventDispatcher()
        received: list[CoreEvent] = []

        dispatcher.subscribe(received.append)
        dispatcher.unsubscribe(received.append)
        dispatcher.publish(CoreEvent(event_type="test_event"))

        self.assertEqual(received, [])

    def test_publishes_without_registered_listeners(self) -> None:
        dispatcher = EventDispatcher()

        dispatcher.publish(CoreEvent(event_type="test_event"))

    def test_keeps_listeners_isolated_between_instances(self) -> None:
        first_dispatcher = EventDispatcher()
        second_dispatcher = EventDispatcher()
        received: list[CoreEvent] = []

        first_dispatcher.subscribe(received.append)
        second_dispatcher.publish(CoreEvent(event_type="test_event"))

        self.assertEqual(received, [])