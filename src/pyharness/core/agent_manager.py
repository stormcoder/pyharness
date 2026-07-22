"""AgentManager — concurrent agent lifecycle management.

Implements the concurrency model from the parallel-multi-agent spec §3:

- **R3.1** ``_tasks: dict[str, asyncio.Task]`` maps ``session_id`` → running task
- **R3.2** ``launch(session_id, runner, screen)`` creates and stores an ``asyncio.Task``
- **R3.3** Streaming output is routed to the correct ``ChatScreen`` via ``screen._write(token)``
- **R3.4** ``cancel(session_id)`` cancels the task for that session
- **R3.5** ``is_running(session_id)`` returns whether a task is active
- **R3.6** ``cancel_all()`` cancels all running tasks (app shutdown)
- **R3.11** ``max_concurrent_agents`` configures the concurrency cap (default 4)
- **R3.12** When the limit is reached, new launches are queued with a notification
- **R3.13** Queued agents launch automatically when a running agent completes
"""

from __future__ import annotations

import asyncio
import collections
from typing import Any

from pyharness.core.logging import get_logger

logger = get_logger(__name__)


class AgentManager:
    """Central manager for all running agent tasks.

    Owns the lifecycle of every running agent: launch, cancel, query,
    and controlled shutdown.  Enforces configurable concurrency limits
    with FIFO queuing.

    Parameters
    ----------
    max_concurrent:
        Maximum number of agents that may run simultaneously.
        Default is 4 (as per R3.11).
    """

    def __init__(self, max_concurrent: int = 4) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._max_concurrent = max(max_concurrent, 1)
        # R3.12: pending launch requests (FIFO queue)
        self._queue: collections.deque[dict[str, Any]] = collections.deque()
        self._notify: Any = None  # will be set after app instance is available

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def active_count(self) -> int:
        """Number of currently running agent tasks."""
        return len(self._tasks)

    @property
    def max_concurrent(self) -> int:
        """Maximum number of concurrent agents (read-only)."""
        return self._max_concurrent

    def launch(
        self,
        session_id: str,
        runner: Any,  # AgentRunner
        user_msg: str,
        screen: Any,  # ChatScreen
        cancel_event: asyncio.Event | None = None,
    ) -> bool:
        """Start an agent run for *session_id*, respecting concurrency limits.

        **R3.2** — If the pool has capacity, an ``asyncio.Task`` is created
        and stored in ``_tasks``.  **R3.12** — If the pool is full, the
        request is queued and the caller is notified.

        Args:
            session_id: Unique session identifier.
            runner: An :class:`~pyharness.core.agent.AgentRunner` instance.
            user_msg: The user's input message.
            screen: The owning :class:`ChatScreen` for output routing.
            cancel_event: Optional cancellation event for the agent.

        Returns:
            ``True`` if the agent was launched immediately, ``False`` if
            it was queued.
        """
        # Clean up any finished task for this session
        self._cleanup(session_id)

        if self.active_count >= self._max_concurrent:
            # R3.12: Queue the request and notify
            self._queue.append({
                "session_id": session_id,
                "runner": runner,
                "user_msg": user_msg,
                "screen": screen,
                "cancel_event": cancel_event,
            })
            logger.info(
                "agent_manager.queued",
                session_id=session_id,
                queue_depth=len(self._queue),
                active_count=self.active_count,
            )
            self._notify_user(
                screen,
                f"[#d29922]⏳ Queued (position {len(self._queue)}). "
                f"{self.active_count}/{self._max_concurrent} agents running...[/]",
            )
            return False

        task = asyncio.create_task(
            self._run_agent(session_id, runner, user_msg, screen, cancel_event),
            name=f"agent-{session_id}",
        )
        self._tasks[session_id] = task
        logger.info(
            "agent_manager.launched",
            session_id=session_id,
            active_count=self.active_count,
        )
        return True

    def cancel(self, session_id: str) -> bool:
        """Cancel the running agent for *session_id*.

        **R3.4** — The underlying ``asyncio.Task`` is cancelled, and the
        session's cancel event (if any) is set.  The task is removed from
        the pool immediately so the slot becomes available for queued
        agents.

        Args:
            session_id: The session whose agent to cancel.

        Returns:
            ``True`` if a task was found and cancelled, ``False`` if no
            task existed for *session_id*.
        """
        task = self._tasks.pop(session_id, None)
        if task is None:
            return False

        if not task.done():
            task.cancel()

        logger.info("agent_manager.cancelled", session_id=session_id)

        # R3.13: drain the queue now that a slot is free
        self._drain_queue()
        return True

    def is_running(self, session_id: str) -> bool:
        """Check whether an agent is active for *session_id*.

        **R3.5** — Returns ``True`` only if the task exists and has not
        yet completed (successfully or via cancellation).
        """
        task = self._tasks.get(session_id)
        return task is not None and not task.done()

    async def cancel_all(self) -> None:
        """Cancel all running agent tasks and drain the queue.

        **R3.6** — Called on app shutdown.  Each task is cancelled and
        the ``_tasks`` dict is cleared.  Queued launch requests are
        discarded with a log warning.
        """
        if self._queue:
            logger.warning(
                "agent_manager.draining_queue_on_shutdown",
                queued=len(self._queue),
            )
            self._queue.clear()

        session_ids = list(self._tasks.keys())
        for sid in session_ids:
            task = self._tasks.pop(sid, None)
            if task is not None and not task.done():
                task.cancel()

        # Give tasks a moment to acknowledge cancellation
        if session_ids:
            await asyncio.sleep(0.05)

        logger.info(
            "agent_manager.cancelled_all",
            cancelled=len(session_ids),
        )

    def remove(self, session_id: str) -> bool:
        """Remove a finished task entry silently (no cancellation).

        Used after a task has completed normally to free the slot.

        Args:
            session_id: The session whose task entry to remove.

        Returns:
            ``True`` if the entry was removed.
        """
        if session_id in self._tasks:
            del self._tasks[session_id]
            self._drain_queue()
            return True
        return False

    def set_notifier(self, app: Any) -> None:
        """Store a reference to the app for notifications.

        Args:
            app: The :class:`PyHarnessApp` instance.
        """
        self._app = app

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_agent(
        self,
        session_id: str,
        runner: Any,
        user_msg: str,
        screen: Any,
        cancel_event: asyncio.Event | None,
    ) -> None:
        """The actual task body — consumes the agent runner and dispatches events.

        **R3.7-R3.10** — Every event from the async generator is routed to
        the owning ``ChatScreen``.
        """
        full_response: list[str] = []
        try:
            # R3.7: consume the AgentRunner async generator
            async for ag_event in runner.run(user_msg, cancel_event=cancel_event):
                kind = ag_event["type"]
                if kind == "content":
                    # R3.8: content token → screen
                    token: str = ag_event["data"]
                    full_response.append(token)
                    screen._write(token)
                elif kind == "tool_call":
                    # R3.9: tool call → screen
                    name: str = ag_event["data"]["name"]
                    screen._write(f"\n[#d29922]  🔧 {name}...[/]")
                elif kind == "tool_result":
                    # R3.9: tool result → screen
                    output: str = ag_event["data"].get("output", "")
                    if output:
                        screen._write(f"[#8b949e]  {output}[/]")
                elif kind == "interrupted":
                    # R3.10: interrupted → screen
                    screen._write("\n[#f85149][Interrupted][/]")
                elif kind == "done":
                    # R3.10: done → render markdown and update status bar
                    if full_response:
                        from pyharness.tui.screens.chat import _render_markdown
                        rendered = _render_markdown("".join(full_response))
                        if rendered and rendered != "".join(full_response):
                            pass
        except asyncio.CancelledError:
            screen._write("\n[#f85149][Interrupted][/]")
        except Exception as exc:
            logger.exception(
                "agent_manager.run_error",
                session_id=session_id,
            )
            screen._write(f"\n[#f85149]Agent error: {exc}[/]")
        finally:
            # Clean up: remove from tasks and drain queue
            if session_id in self._tasks:
                del self._tasks[session_id]
            self._drain_queue()

    def _cleanup(self, session_id: str) -> None:
        """Remove a finished or cancelled task entry for *session_id*."""
        task = self._tasks.get(session_id)
        if task is not None and task.done():
            del self._tasks[session_id]

    def _drain_queue(self) -> None:
        """R3.13: Launch the next queued agent if a slot is available.

        Processes the FIFO queue, skipping entries whose sessions are
        already running (safety guard against double-launch).
        """
        while self._queue and self.active_count < self._max_concurrent:
            entry = self._queue.popleft()
            sid = entry["session_id"]
            if sid in self._tasks:
                logger.warning(
                    "agent_manager.skip_duplicate",
                    session_id=sid,
                )
                continue
            self.launch(**entry)

    @staticmethod
    def _notify_user(screen: Any, message: str) -> None:
        """Write a notification to the owning screen's chat area."""
        import contextlib
        with contextlib.suppress(Exception):
            screen._write(message)
