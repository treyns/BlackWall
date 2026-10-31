import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.models import PerfSample
from performance.adaptive import AdaptiveQualityController


class _Settings:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def get(self, key: str, default=None):
        if key == "performance.adaptive_quality":
            return self.enabled
        return default


def sample(fps: float, gpu=20.0, system_cpu=40.0, app_cpu=5.0) -> PerfSample:
    return PerfSample(fps=fps, gpu=gpu, system_cpu=system_cpu, cpu=app_cpu)


class AdaptiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.controller = AdaptiveQualityController(_Settings(True))

    def test_disabled_never_changes(self) -> None:
        controller = AdaptiveQualityController(_Settings(False))
        for index in range(50):
            self.assertIsNone(controller.update(sample(2), 30.0, True, now=index))

    def test_downgrade_needs_three_slow_samples(self) -> None:
        now = 100.0
        self.assertIsNone(self.controller.update(sample(5), 30.0, True, now=now))
        self.assertIsNone(self.controller.update(sample(5), 30.0, True, now=now + 1))
        self.assertEqual(self.controller.update(sample(5), 30.0, True, now=now + 2), 1)
        self.assertEqual(self.controller.level, 1)

    def test_cooldown_prevents_immediate_second_downgrade(self) -> None:
        now = 100.0
        for tick in range(3):
            changed = self.controller.update(sample(5), 30.0, True, now=now + tick)
        self.assertEqual(changed, 1)
        # immediately slow again, but the cooldown must block the change
        for tick in range(4):
            self.assertIsNone(self.controller.update(sample(5), 30.0, True,
                                                     now=now + 3 + tick))
        self.assertEqual(self.controller.level, 1)
        changed = self.controller.update(sample(5), 30.0, True, now=now + 20)
        self.assertEqual(changed, 2)

    def test_no_oscillation_when_samples_alternate(self) -> None:
        now = 100.0
        for tick in range(3):
            self.controller.update(sample(5), 30.0, True, now=now + tick)
        self.assertEqual(self.controller.level, 1)
        # alternating good/bad samples never reach the consecutive thresholds
        for tick in range(10):
            self.controller.update(sample(30 if tick % 2 == 0 else 5), 30.0, True,
                                   now=now + 20 + tick)
        self.assertEqual(self.controller.level, 1)

    def test_upgrade_after_long_health_and_trial(self) -> None:
        now = 100.0
        for tick in range(3):
            self.controller.update(sample(5), 30.0, True, now=now + tick)
        self.assertEqual(self.controller.level, 1)
        # enough healthy samples, respecting cooldown and required 25 samples
        upgrade = None
        for tick in range(60):
            moment = now + 30 + tick
            result = self.controller.update(sample(30), 30.0, True, now=moment)
            if result is not None:
                upgrade = result
                break
        self.assertEqual(upgrade, 0)
        # trial period: a slow sample immediately rolls the upgrade back
        changed = self.controller.update(sample(5), 30.0, True, now=now + 95)
        self.assertEqual(changed, 1)
        self.assertEqual(self.controller.level, 1)
        self.assertEqual(self.controller._failed_trials, 1)

    def test_upgrade_blocked_after_two_failed_trials(self) -> None:
        now = 100.0
        for tick in range(3):
            self.controller.update(sample(5), 30.0, True, now=now + tick)
        self.assertEqual(self.controller.level, 1)

        def reach_upgrade(start: float) -> float | None:
            for tick in range(120):
                moment = start + tick
                result = self.controller.update(sample(30), 30.0, True, now=moment)
                if result is not None:
                    return moment
            return None

        first = reach_upgrade(now + 30)
        self.assertIsNotNone(first)
        self.assertEqual(self.controller.level, 0)
        self.controller.update(sample(4), 30.0, True, now=first + 1)
        self.assertEqual(self.controller.level, 1)
        self.assertEqual(self.controller._failed_trials, 1)
        block = self.controller._upgrade_block_until
        self.assertGreater(block, first)

        second = reach_upgrade(block + 5)
        self.assertIsNotNone(second)
        self.assertEqual(self.controller.level, 0)
        self.controller.update(sample(4), 30.0, True, now=second + 1)
        self.assertEqual(self.controller.level, 1)
        self.assertEqual(self.controller._failed_trials, 2)
        self.assertEqual(self.controller._upgrade_block_until, float("inf"))

    def test_paused_does_not_change(self) -> None:
        self.assertIsNone(self.controller.update(sample(1), 30.0, False, now=100.0))
        self.assertEqual(self.controller.level, 0)


if __name__ == "__main__":
    unittest.main()
