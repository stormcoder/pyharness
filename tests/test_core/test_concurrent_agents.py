"""Concurrent agent stress tests for AgentManager.

Covers:
- Launch 3 agents simultaneously via AgentManager
- Verify all 3 complete without errors
- Verify each agent's output goes to the correct screen (mock screens)
- Verify queue behavior when max_concurrent is exceeded
- Verify cancel_all() stops all running agents
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from pyharness.core.agent_manager import AgentManager

# ---------------------------------------------------------------------------
# Fake runner for testing
# ---------------------------------------------------------------------------


class FakeRunner:
    """Minimal AgentRunner stand-in with configurable events and delay.

    Parameters
    ----------
    events:
        Pre-scripted events to yield during ``run()``.
    delay:
        Seconds to sleep between each event yield (simulates work).
    name:
        Identifier used in content to distinguish runners.
    """

    def __init__(
        self,
        events: list[dict] | None = None,
        delay: float = 0.02,
        name: str = "",
    ) -> None:
        self.events = events or [
            {"type": "content", "data": "Hello"},
            {"type": "done", "data": None},
        ]
        self.delay = delay
        self.name = name
        self.run_called = False
        self.run_user_msg: str = ""
        self.cancelled = False

    async def run(
        self,
        user_msg: str = "",
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncIterator[dict]:
        """Simulate AgentRunner.run() with configurable delay."""
        self.run_called = True
        self.run_user_msg = user_msg
        self.cancelled = False
        for ev in self.events:
            if cancel_event is not None and cancel_event.is_set():
                self.cancelled = True
                yield {"type": "interrupted", "data": None}
                return
            yield ev
            await asyncio.sleep(self.delay)

    def spawn_subagent(self, agent_type: str, prompt: str, session_id: str) -> str:
        """Stub spawn_subagent."""
        return f"spawned {agent_type}"


class FakeScreen:
    """Minimal ChatScreen stand-in for testing routing.

    Each FakeScreen is tagged with a ``screen_id`` so we can verify
    that events from different sessions go to the right screen.
    """

    def __init__(self, screen_id: str = "") -> None:
        self.output: list[str] = []
        self.screen_id = screen_id

    def _write(self, text: str) -> None:
        self.output.append(text)


# ---------------------------------------------------------------------------
# Tests: concurrent agent launches
# ---------------------------------------------------------------------------


class TestConcurrentAgentLaunch:
    """Verify that multiple agents can be launched simultaneously."""

    @pytest.mark.asyncio
    async def test_3_agents_complete_without_errors(self) -> None:
        """Launch 3 agents — all complete successfully."""
        mgr = AgentManager(max_concurrent=5)
        screens = [FakeScreen(screen_id=f"screen-{i}") for i in range(3)]

        for i in range(3):
            runner = FakeRunner(
                events=[
                    {"type": "content", "data": f"Agent {i} start"},
                    {"type": "content", "data": f" Agent {i} end"},
                    {"type": "done", "data": None},
                ],
                name=f"runner-{i}",
            )
            mgr.launch(f"session-{i}", runner, f"msg from {i}", screens[i])

        # Wait for all to complete
        await asyncio.sleep(0.3)

        # No agents should still be running
        for i in range(3):
            assert not mgr.is_running(f"session-{i}"), (
                f"Session {i} should have completed"
            )

        # Each screen should have received the output
        for i, screen in enumerate(screens):
            combined = "".join(screen.output)
            assert f"Agent {i} start" in combined
            assert f"Agent {i} end" in combined

    @pytest.mark.asyncio
    async def test_output_routes_to_correct_screen(self) -> None:
        """Each agent's output goes to its OWN screen, not others'."""
        mgr = AgentManager(max_concurrent=5)
        screen_a = FakeScreen(screen_id="screen-a")
        screen_b = FakeScreen(screen_id="screen-b")

        runner_a = FakeRunner(
            events=[
                {"type": "content", "data": "AAA"},
                {"type": "done", "data": None},
            ],
            name="a",
        )
        runner_b = FakeRunner(
            events=[
                {"type": "content", "data": "BBB"},
                {"type": "done", "data": None},
            ],
            name="b",
        )

        mgr.launch("session-a", runner_a, "msg a", screen_a)
        mgr.launch("session-b", runner_b, "msg b", screen_b)

        await asyncio.sleep(0.2)

        combined_a = "".join(screen_a.output)
        combined_b = "".join(screen_b.output)

        # Screen A has A's content, not B's
        assert "AAA" in combined_a
        assert "BBB" not in combined_a

        # Screen B has B's content, not A's
        assert "BBB" in combined_b
        assert "AAA" not in combined_b

    @pytest.mark.asyncio
    async def test_agents_run_concurrently(self) -> None:
        """Agents actually run concurrently (not sequentially)."""
        mgr = AgentManager(max_concurrent=5)

        # Use slow runners to ensure overlap
        screens = [FakeScreen(f"concurrent-{i}") for i in range(3)]
        runners = [
            FakeRunner(
                events=[
                    {"type": "content", "data": f"C{i}"},
                    {"type": "done", "data": None},
                ],
                delay=0.05,
                name=f"conc-{i}",
            )
            for i in range(3)
        ]

        for i in range(3):
            mgr.launch(f"conc-{i}", runners[i], f"msg{i}", screens[i])

        # Wait briefly — if sequential, only 1 would complete
        await asyncio.sleep(0.1)

        # All should have made progress (at least started or finished)
        # Since they run concurrently with short delays, all should complete
        await asyncio.sleep(0.1)

        all_done = all(
            not mgr.is_running(f"conc-{i}") for i in range(3)
        )
        assert all_done, "All concurrent agents should complete within timeout"


# ---------------------------------------------------------------------------
# Tests: queuing when max_concurrent is exceeded
# ---------------------------------------------------------------------------


class TestAgentQueueing:
    """Verify queue behavior when concurrent limit is exceeded."""

    @pytest.mark.asyncio
    async def test_launch_returns_false_when_queued(self) -> None:
        """R3.12: launch returns False when queued."""
        mgr = AgentManager(max_concurrent=2)
        screen = FakeScreen()

        # Fill pool
        slow = FakeRunner(
            events=[{"type": "content", "data": "X"}] * 500,
            delay=0.01,
        )
        mgr.launch("s0", slow, "m0", screen)
        mgr.launch("s1", slow, "m1", screen)

        assert mgr.active_count == 2

        # Third launch should be queued
        result = mgr.launch("s2", slow, "m2", screen)
        assert result is False
        assert len(mgr._queue) == 1

    @pytest.mark.asyncio
    async def test_queue_notification_sent(self) -> None:
        """R3.12: screen receives queue notification."""
        mgr = AgentManager(max_concurrent=1)
        screen = FakeScreen()

        slow = FakeRunner(
            events=[{"type": "content", "data": "X"}] * 500,
        )
        mgr.launch("s0", slow, "m0", screen)

        assert mgr.active_count == 1

        # Second launch queued
        mgr.launch("s1", slow, "m1", screen)

        combined = "".join(screen.output)
        assert "Queued" in combined

    @pytest.mark.asyncio
    async def test_queue_drains_on_completion(self) -> None:
        """R3.13: queued agents launch when a running agent completes."""
        mgr = AgentManager(max_concurrent=2)
        screen = FakeScreen()

        # Fill with slow runners
        slow = FakeRunner(
            events=[{"type": "content", "data": "X"}] * 500,
            delay=0.01,
        )
        mgr.launch("s0", slow, "m0", screen)
        mgr.launch("s1", slow, "m1", screen)

        # Queue a fast runner
        fast = FakeRunner(
            events=[
                {"type": "content", "data": "QUEUED_RUN"},
                {"type": "done", "data": None},
            ],
            name="queued",
        )
        mgr.launch("s2", fast, "m2", screen)

        # Cancel one to free a slot → queued runs
        mgr.cancel("s0")
        await asyncio.sleep(0.3)

        combined = "".join(screen.output)
        assert "QUEUED_RUN" in combined

    @pytest.mark.asyncio
    async def test_queue_skips_duplicates(self) -> None:
        """Queue drain skips sessions already running (safety guard)."""
        mgr = AgentManager(max_concurrent=1)
        screen = FakeScreen()

        # Launch one and queue one
        slow = FakeRunner(
            events=[{"type": "content", "data": "X"}] * 300,
            delay=0.01,
        )
        mgr.launch("s0", slow, "m0", screen)
        mgr.launch("s1", slow, "m1", screen)

        # Manually put a duplicate entry in the queue
        mgr._queue.append({
            "session_id": "s0",
            "runner": slow,
            "user_msg": "dup",
            "screen": screen,
            "cancel_event": None,
        })

        # Cancel s0 — should drain queue but skip duplicate s0
        mgr.cancel("s0")
        await asyncio.sleep(0.2)

        # s1 should have launched (the legitimate queued entry)
        assert not mgr.is_running("s0")

    @pytest.mark.asyncio
    async def test_fifo_queue_ordering(self) -> None:
        """Queue processes in FIFO order."""
        mgr = AgentManager(max_concurrent=1)
        screen = FakeScreen()

        # Fill the single slot
        slow = FakeRunner(
            events=[{"type": "content", "data": "X"}] * 300,
            delay=0.01,
        )
        mgr.launch("s0", slow, "m0", screen)

        # Queue two items
        runner1 = FakeRunner(
            events=[
                {"type": "content", "data": "FIRST"},
                {"type": "done", "data": None},
            ],
            name="first",
        )
        runner2 = FakeRunner(
            events=[
                {"type": "content", "data": "SECOND"},
                {"type": "done", "data": None},
            ],
            name="second",
        )
        mgr.launch("s1", runner1, "m1", screen)
        mgr.launch("s2", runner2, "m2", screen)

        # Cancel s0 — queue drains: s1 then s2
        mgr.cancel("s0")
        await asyncio.sleep(0.3)

        combined = "".join(screen.output)
        first_idx = combined.find("FIRST")
        second_idx = combined.find("SECOND")
        assert first_idx >= 0, "FIRST should appear in output"
        assert second_idx >= 0, "SECOND should appear in output"
        assert first_idx < second_idx, "FIRST should appear before SECOND"


# ---------------------------------------------------------------------------
# Tests: cancel_all
# ---------------------------------------------------------------------------


class TestCancelAll:
    """Verify cancel_all() stops everything."""

    @pytest.mark.asyncio
    async def test_cancel_all_stops_all_running(self) -> None:
        """R3.6: cancel_all() stops all running agents."""
        mgr = AgentManager(max_concurrent=5)
        screen = FakeScreen()

        # Launch 4 slow agents
        for i in range(4):
            slow = FakeRunner(
                events=[{"type": "content", "data": f"X{i}"}] * 2000,
                delay=0.01,
            )
            mgr.launch(f"s{i}", slow, f"msg{i}", screen)

        assert mgr.active_count == 4

        await mgr.cancel_all()

        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_cancel_all_drains_queue(self) -> None:
        """R3.6: cancel_all() clears the pending queue."""
        mgr = AgentManager(max_concurrent=2)
        screen = FakeScreen()

        slow = FakeRunner(
            events=[{"type": "content", "data": "X"}] * 2000,
        )
        mgr.launch("s0", slow, "m0", screen)
        mgr.launch("s1", slow, "m1", screen)

        # Queue one
        mgr.launch("s2", slow, "m2", screen)
        assert len(mgr._queue) == 1

        await mgr.cancel_all()

        assert mgr.active_count == 0
        assert len(mgr._queue) == 0

    @pytest.mark.asyncio
    async def test_cancel_all_idempotent(self) -> None:
        """cancel_all() on an empty manager does not raise."""
        mgr = AgentManager()
        await mgr.cancel_all()  # Should not raise
        assert mgr.active_count == 0


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------


class TestConcurrentEdgeCases:
    """Edge cases for concurrent agent management."""

    @pytest.mark.asyncio
    async def test_launch_cleans_up_finished_task(self) -> None:
        """Re-launching for the same session after completion works."""
        mgr = AgentManager()
        screen = FakeScreen()

        # First launch: fast runner
        fast = FakeRunner(
            events=[{"type": "done", "data": None}],
            name="first",
        )
        mgr.launch("s1", fast, "m1", screen)
        await asyncio.sleep(0.1)

        assert not mgr.is_running("s1")

        # Second launch: should work without issues
        fast2 = FakeRunner(
            events=[{"type": "content", "data": "second_run"},
                    {"type": "done", "data": None}],
            name="second",
        )
        result = mgr.launch("s1", fast2, "m2", screen)
        assert result is True

        await asyncio.sleep(0.1)
        combined = "".join(screen.output)
        assert "second_run" in combined

    @pytest.mark.asyncio
    async def test_remove_frees_slot(self) -> None:
        """remove() frees a slot for queued agents."""
        mgr = AgentManager(max_concurrent=1)
        screen = FakeScreen()

        slow = FakeRunner(
            events=[{"type": "content", "data": "X"}] * 300,
            delay=0.01,
        )
        mgr.launch("s0", slow, "m0", screen)
        assert mgr.active_count == 1

        # Queue one
        fast = FakeRunner(
            events=[
                {"type": "content", "data": "QUEUED_REMOVED"},
                {"type": "done", "data": None},
            ],
        )
        mgr.launch("s1", fast, "m1", screen)
        assert len(mgr._queue) == 1

        # Remove the running task (simulating completion)
        removed = mgr.remove("s0")
        assert removed

        await asyncio.sleep(0.2)
        combined = "".join(screen.output)
        assert "QUEUED_REMOVED" in combined

    @pytest.mark.asyncio
    async def test_remove_unknown_session(self) -> None:
        """remove() on unknown session returns False."""
        mgr = AgentManager()
        assert not mgr.remove("bogus")

    @pytest.mark.asyncio
    async def test_multiple_cancel_same_session(self) -> None:
        """Cancelling the same session twice returns False second time."""
        mgr = AgentManager()
        screen = FakeScreen()

        slow = FakeRunner(
            events=[{"type": "content", "data": "X"}] * 500,
            delay=0.01,
        )
        mgr.launch("s1", slow, "m1", screen)

        assert mgr.cancel("s1")
        assert not mgr.cancel("s1")  # Already cancelled

    @pytest.mark.asyncio
    async def test_active_count_reflects_running_only(self) -> None:
        """active_count only counts currently-running tasks, not completed."""
        mgr = AgentManager(max_concurrent=3)
        screen = FakeScreen()

        # Launch three
        for i in range(3):
            fast = FakeRunner(
                events=[{"type": "done", "data": None}],
                name=f"fast-{i}",
            )
            mgr.launch(f"s{i}", fast, f"m{i}", screen)

        await asyncio.sleep(0.2)

        # All should be done
        assert mgr.active_count == 0

    @pytest.mark.asyncio
    async def test_fast_agents_dont_block_slow(self) -> None:
        """A fast agent finishes without blocking a slow agent."""
        mgr = AgentManager(max_concurrent=2)
        screen = FakeScreen()

        slow = FakeRunner(
            events=[
                {"type": "content", "data": "slow_start"},
                {"type": "content", "data": "slow_mid"},
                {"type": "content", "data": "slow_end"},
                {"type": "done", "data": None},
            ],
            delay=0.05,
            name="slow",
        )
        fast = FakeRunner(
            events=[
                {"type": "content", "data": "fast_done"},
                {"type": "done", "data": None},
            ],
            delay=0.01,
            name="fast",
        )

        mgr.launch("slow", slow, "msg", screen)
        mgr.launch("fast", fast, "msg", screen)

        await asyncio.sleep(0.3)

        # Both should complete
        assert not mgr.is_running("slow")
        assert not mgr.is_running("fast")

        combined = "".join(screen.output)
        assert "fast_done" in combined
        assert "slow_end" in combined
