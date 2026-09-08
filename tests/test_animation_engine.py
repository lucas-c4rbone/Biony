import unittest

from face.animation_engine import AnimationEngine, AnimationFrame, OFFICIAL_ANIMATIONS, PixelAnimation


class AnimationEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frames: list[AnimationFrame | None] = []
        self.finished: list[str] = []
        self.engine = AnimationEngine(self.frames.append, self.finished.append)

    def test_official_animations_have_explicit_frames(self) -> None:
        expected = {
            "hammer", "look_left_right", "look_up", "meditation", "octane",
            "pesqueiro", "quick_glitch", "running", "spaghetti_hunter", "yawn",
        }

        self.assertEqual(set(OFFICIAL_ANIMATIONS), expected)
        self.assertTrue(all(animation.frames for animation in OFFICIAL_ANIMATIONS.values()))

    def test_frames_run_in_declared_order(self) -> None:
        animation = OFFICIAL_ANIMATIONS["look_left_right"]

        self.engine.start(animation.name)
        for _ in range(len(animation.frames) - 1):
            self.engine.advance_for_test()

        self.assertEqual(self.frames, list(animation.frames))

    def test_frame_duration_is_structurally_preserved(self) -> None:
        frame = OFFICIAL_ANIMATIONS["quick_glitch"].frames[0]

        self.assertEqual(frame.duration_ms, 90)
        self.assertGreater(frame.duration_ms, 0)

    def test_one_shot_animation_finishes(self) -> None:
        animation = OFFICIAL_ANIMATIONS["yawn"]

        self.engine.start(animation.name)
        for _ in range(len(animation.frames)):
            self.engine.advance_for_test()

        self.assertFalse(self.engine.is_running)
        self.assertEqual(self.finished, ["yawn"])
        self.assertIsNone(self.frames[-1])

    def test_loop_animation_restarts(self) -> None:
        animation = PixelAnimation(
            "loop", (AnimationFrame(((1, 1, "blue"),), 1), AnimationFrame(((2, 1, "blue"),), 1)), True
        )
        OFFICIAL_ANIMATIONS["loop"] = animation
        self.addCleanup(OFFICIAL_ANIMATIONS.pop, "loop", None)

        self.engine.start("loop")
        self.engine.advance_for_test()
        self.engine.advance_for_test()

        self.assertTrue(self.engine.is_running)
        self.assertEqual(self.frames[:3], list(animation.frames) + [animation.frames[0]])

    def test_animation_can_be_interrupted(self) -> None:
        self.engine.start("meditation")
        self.engine.stop()
        self.engine.advance_for_test()

        self.assertFalse(self.engine.is_running)
        self.assertEqual(self.finished, ["meditation"])
        self.assertIsNone(self.frames[-1])

    def test_new_animation_replaces_the_previous_one(self) -> None:
        self.engine.start("meditation")
        self.engine.start("yawn")

        self.assertEqual(self.engine.current_animation, "yawn")
        self.assertEqual(self.frames[-1], OFFICIAL_ANIMATIONS["yawn"].frames[0])

    def test_unknown_animation_raises_an_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown Biony animation"):
            self.engine.start("not_an_animation")

    def test_engine_uses_a_qtimer_instead_of_blocking(self) -> None:
        self.engine.start("look_up")

        self.assertTrue(self.engine._timer.isSingleShot())
        self.assertEqual(
            self.engine._timer.interval(),
            OFFICIAL_ANIMATIONS["look_up"].frames[0].duration_ms,
        )