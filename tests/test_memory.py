from pathlib import Path
import unittest

from core.memory import InMemoryMemoryStore
from core.models import Memory


class InMemoryMemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryMemoryStore()

    def test_starts_without_memories(self) -> None:
        self.assertEqual(self.store.list_all(), [])
        self.assertEqual(self.store.search("qualquer texto"), [])

    def test_saves_and_lists_a_memory(self) -> None:
        memory = Memory(content="Comprar filamento preto")

        self.store.save(memory)

        self.assertEqual(self.store.list_all(), [memory])

    def test_searches_memories_by_content(self) -> None:
        expected = Memory(content="Comprar filamento preto")
        self.store.save(expected)
        self.store.save(Memory(content="Testar a câmera"))

        found = self.store.search("FILAMENTO")

        self.assertEqual(found, [expected])

    def test_removes_a_memory(self) -> None:
        memory = Memory(content="Comprar filamento preto")
        self.store.save(memory)

        removed = self.store.remove(memory)

        self.assertTrue(removed)
        self.assertEqual(self.store.list_all(), [])

    def test_clears_all_memories(self) -> None:
        self.store.save(Memory(content="Comprar filamento preto"))
        self.store.save(Memory(content="Testar a câmera"))

        self.store.clear()

        self.assertEqual(self.store.list_all(), [])

    def test_does_not_depend_on_pyside6(self) -> None:
        source = Path("core/memory.py").read_text(encoding="utf-8")

        self.assertNotIn("PySide6", source)