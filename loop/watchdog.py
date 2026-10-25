"""Watchdog: stuck detection and budget enforcement.

For the demo: log loudly and end the episode. No auto-recovery.
"""

import time
from enum import Enum


class WatchdogAction(Enum):
    CONTINUE          = "continue"
    END_EPISODE       = "end_episode"
    RESTART_CHARGEN   = "restart_chargen"


class Watchdog:
    # Episode budgets
    MAX_TURNS       = 5000
    MAX_EPISODE_SECONDS = 2 * 3600  # 2 hours

    # Stuck detection
    # "Same screen" for play mode means the model stayed on the play screen
    # without the screen label changing — but "play" IS the normal game screen
    # and doesn't change when moving around. Use a high threshold and rely
    # primarily on the anti-repeat system + no-log-change streak.
    SAME_SCREEN_TURNS = 100
    NO_LOG_CHANGE_TURNS = 30  # consecutive turns with no log change = stuck

    # Chargen budgets
    CHARGEN_MAX_STEPS    = 100
    CHARGEN_MAX_SECONDS  = 600   # 10 minutes
    CHARGEN_NO_PROGRESS  = 30    # steps without screen change

    def __init__(self) -> None:
        self.last_screen: str = ""
        self.same_screen_count: int = 0
        self.no_log_streak: int = 0
        self.episode_start_time: float = 0.0
        self.episode_start_turn: int = 0
        # Chargen tracking
        self.chargen_step_count: int = 0
        self.chargen_start_time: float = 0.0
        self.chargen_last_screen: str = ""
        self.chargen_no_progress: int = 0

    def start_episode(self) -> None:
        self.episode_start_time = time.monotonic()
        self.episode_start_turn = 0
        self.same_screen_count = 0
        self.no_log_streak = 0
        self.last_screen = ""

    def start_chargen(self) -> None:
        self.chargen_step_count = 0
        self.chargen_start_time = time.monotonic()
        self.chargen_last_screen = ""
        self.chargen_no_progress = 0

    def check_play(self, screen: str, turn_count: int, turn_changed: bool) -> WatchdogAction:
        """Check play-phase watchdog. Called every turn."""
        # Same screen streak
        if screen == self.last_screen:
            self.same_screen_count += 1
        else:
            self.same_screen_count = 0
            self.last_screen = screen
        if self.same_screen_count >= self.SAME_SCREEN_TURNS:
            print(f"[watchdog] Stuck: same screen '{screen}' for {self.same_screen_count} turns")
            return WatchdogAction.END_EPISODE

        # Track consecutive no-log-change turns. The log doesn't always update
        # (bumping into a wall), but 30+ consecutive turns with no log change
        # means the model is truly stuck (wandering in circles, blocked, etc.)
        if not turn_changed:
            self.no_log_streak += 1
        else:
            self.no_log_streak = 0
        if self.no_log_streak >= self.NO_LOG_CHANGE_TURNS:
            print(f"[watchdog] Stuck: no log change for {self.no_log_streak} turns")
            return WatchdogAction.END_EPISODE

        # Turn budget
        if turn_count - self.episode_start_turn >= self.MAX_TURNS:
            print(f"[watchdog] Turn budget exceeded: {turn_count} turns")
            return WatchdogAction.END_EPISODE

        # Time budget
        elapsed = time.monotonic() - self.episode_start_time
        if elapsed >= self.MAX_EPISODE_SECONDS:
            print(f"[watchdog] Time budget exceeded: {elapsed / 3600:.1f} hours")
            return WatchdogAction.END_EPISODE

        return WatchdogAction.CONTINUE

    def check_chargen(self, screen: str) -> WatchdogAction:
        """Check chargen watchdog. Called every chargen step."""
        self.chargen_step_count += 1

        # No progress
        if screen == self.chargen_last_screen:
            self.chargen_no_progress += 1
        else:
            self.chargen_no_progress = 0
            self.chargen_last_screen = screen
        if self.chargen_no_progress >= self.CHARGEN_NO_PROGRESS:
            print(f"[watchdog] Chargen stuck: no progress for {self.chargen_no_progress} steps")
            return WatchdogAction.RESTART_CHARGEN

        # Step budget
        if self.chargen_step_count >= self.CHARGEN_MAX_STEPS:
            print(f"[watchdog] Chargen step budget exceeded: {self.chargen_step_count} steps")
            return WatchdogAction.RESTART_CHARGEN

        # Time budget
        elapsed = time.monotonic() - self.chargen_start_time
        if elapsed >= self.CHARGEN_MAX_SECONDS:
            print(f"[watchdog] Chargen time budget exceeded: {elapsed / 60:.1f} min")
            return WatchdogAction.RESTART_CHARGEN

        return WatchdogAction.CONTINUE

    def reset(self) -> None:
        self.last_screen = ""
        self.same_screen_count = 0
        self.no_log_streak = 0
        self.chargen_step_count = 0
        self.chargen_no_progress = 0
        self.chargen_last_screen = ""


# Singleton
_watchdog = Watchdog()


def get_watchdog() -> Watchdog:
    return _watchdog
