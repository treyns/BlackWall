"""Adaptive playback quality: step quality down under load and back up later.

The controller is deliberately conservative: it needs several consecutive
"slow" samples before reducing quality and a long healthy period before
increasing it again, with a cooldown between changes, so quality never
oscillates back and forth.
"""
from __future__ import annotations

import time

LEVEL_SCALE = {0: 1.0, 1: 0.85, 2: 0.7}
LEVEL_FPS = {0: 1.0, 1: 0.66, 2: 0.5}

# Number of 1-second samples required before a change.
LOW_SAMPLES = 3
HIGH_SAMPLES = 25
COOLDOWN_SECONDS = 8.0


class AdaptiveQualityController:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.level = 0
        self._low = 0
        self._high = 0
        self._last_change = 0.0
        self._last_upgrade = 0.0
        self._upgrade_backoff = 1
        self._trial_until = 0.0
        self._trial_from = 0
        self._upgrade_block_until = 0.0
        self._failed_trials = 0

    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("performance.adaptive_quality", True))

    @property
    def render_scale(self) -> float:
        return LEVEL_SCALE.get(self.level, 1.0)

    @property
    def fps_multiplier(self) -> float:
        return LEVEL_FPS.get(self.level, 1.0)

    def reset(self) -> None:
        self.level = 0
        self._low = 0
        self._high = 0
        self._trial_until = 0.0
        self._trial_from = 0
        self._upgrade_block_until = 0.0
        self._failed_trials = 0
        self._upgrade_backoff = 1

    def update(self, sample, target_fps: float, active: bool,
               now: float | None = None) -> int | None:
        """Feed one measurement. Returns a new level (0..2) when it changes."""
        now = time.monotonic() if now is None else float(now)

        if not self.enabled:
            self._low = 0
            self._high = 0
            self._trial_until = 0.0
            if self.level != 0:
                self.level = 0
                self._last_change = now
                return 0
            return None

        if not active or target_fps <= 0:
            # Nothing is playing (paused, no wallpaper) - do not change quality.
            self._low = 0
            self._high = 0
            return None

        ratio = float(sample.fps or 0.0) / float(target_fps)
        gpu = sample.gpu
        system_cpu = float(sample.system_cpu or 0.0)
        app_cpu = float(sample.cpu or 0.0)

        lagging = (
            (sample.fps > 0 and ratio < 0.70)
            or (gpu is not None and gpu >= 92.0)
            or system_cpu >= 88.0
            or app_cpu >= 22.0
        )
        healthy = (
            ratio >= 0.90
            and (gpu is None or gpu < 70.0)
            and system_cpu < 70.0
            and app_cpu < 12.0
        )

        # A quality upgrade is first tried for a short while; if the load comes
        # back immediately, the upgrade is rolled back and blocked for a while.
        if self._trial_until:
            if lagging:
                self.level = self._trial_from
                self._trial_until = 0.0
                self._low = 0
                self._high = 0
                self._failed_trials += 1
                self._upgrade_backoff = 4
                if self._failed_trials >= 2:
                    self._upgrade_block_until = float("inf")
                else:
                    self._upgrade_block_until = now + 600.0
                self._last_change = now
                return self.level
            if now >= self._trial_until:
                self._trial_until = 0.0
                self._failed_trials = 0

        if lagging:
            self._low += 1
            self._high = 0
        elif healthy:
            self._high += 1
            self._low = 0
        else:
            self._low = 0
            self._high = 0

        if now - self._last_change < COOLDOWN_SECONDS:
            return None

        required_high = HIGH_SAMPLES * self._upgrade_backoff
        if self._low >= LOW_SAMPLES and self.level < 2:
            self.level += 1
            self._low = 0
            self._trial_until = 0.0
            if self._last_upgrade and now - self._last_upgrade < 120.0:
                # The previous upgrade did not stick - wait longer next time.
                self._upgrade_backoff = min(4, self._upgrade_backoff * 2)
            self._last_change = now
            return self.level
        if (self._high >= required_high and self.level > 0
                and now >= self._upgrade_block_until):
            previous = self.level
            self.level -= 1
            self._high = 0
            self._last_upgrade = now
            self._last_change = now
            self._trial_from = previous
            self._trial_until = now + 10.0
            return self.level
        if (self.level > 0 and self._high >= HIGH_SAMPLES
                and self._last_upgrade and now - self._last_upgrade > 120.0):
            # A long stable period at the higher quality: allow faster upgrades.
            self._upgrade_backoff = max(1, self._upgrade_backoff // 2)
        return None
