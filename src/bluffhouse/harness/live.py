"""Live games for the web app: one table on a worker thread, ground-truth
events streamed to the browser as they are emitted.

API keys arrive with the request, go straight into client constructors, and
are never written to disk. Stop is abandonment: the thread unwinds at the
next agent decision and no run directory is written. A finished game is
written to the runs directory like any other and gets a full replay.
"""

import json
import queue
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from bluffhouse.agents.base import Agent
from bluffhouse.harness.game import GameHarness, GameResult
from bluffhouse.models import (
    AgentView,
    AttentionPlan,
    CommunicationAction,
    HandEnded,
    Observation,
    PokerAction,
    TableConfig,
)

Frame = tuple[str, int | None, str | None]  # (kind, seq, data)


class LiveStopped(Exception):
    """The user pressed stop; unwind the game thread."""


@dataclass
class LiveJob:
    id: str
    config: TableConfig
    history: list[tuple[int, str]] = field(default_factory=list)
    listeners: list[queue.SimpleQueue] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    status: str = "running"  # running | done | stopped | error
    error: str | None = None
    run_dir: str | None = None  # relative to the runs root, set when written
    activity: dict | None = None  # who is thinking right now
    stop_requested: bool = False
    thread: threading.Thread | None = None

    def _fanout(self, frame: Frame) -> None:
        for q in self.listeners:
            q.put(frame)

    def emit_event(self, seq: int, data: str) -> None:
        with self.lock:
            self.history.append((seq, data))
            self._fanout(("event", seq, data))

    def emit_status(self, activity: dict) -> None:
        with self.lock:
            self.activity = activity
            self._fanout(("status", None, json.dumps(activity)))

    def finish(self) -> None:
        with self.lock:
            self._fanout(("done", None, None))

    def subscribe(self) -> tuple[list[tuple[int, str]], queue.SimpleQueue]:
        q: queue.SimpleQueue = queue.SimpleQueue()
        with self.lock:
            backlog = list(self.history)
            self.listeners.append(q)
        return backlog, q

    def unsubscribe(self, q: queue.SimpleQueue) -> None:
        with self.lock:
            if q in self.listeners:
                self.listeners.remove(q)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "job": self.id,
                "status": self.status,
                "error": self.error,
                "run_dir": self.run_dir,
                "events": len(self.history),
                "activity": self.activity,
                "agent_ids": list(self.config.agent_ids),
            }


class _Watched(Agent):
    """Wraps a seat: reports who is thinking, honors the stop flag."""

    def __init__(self, inner: Agent, job: LiveJob):
        super().__init__(inner.id)
        self._inner = inner
        self._job = job

    @property
    def transcript(self):
        # the harness collects LLM transcripts via getattr(agent, "transcript")
        # — pass the wrapped seat's through or live runs lose their llm/*.jsonl
        return getattr(self._inner, "transcript", None)

    def _mark(self, phase: str, view: AgentView) -> None:
        if self._job.stop_requested:
            raise LiveStopped()
        self._job.emit_status({
            "agent": self.id,
            "phase": phase,
            "hand": view.table.hand_no,
            "street": view.table.street,
        })

    def observe(self, observation: Observation) -> None:
        self._inner.observe(observation)

    def attend(self, view: AgentView) -> AttentionPlan | None:
        self._mark("attention", view)
        return self._inner.attend(view)

    def communicate(self, view: AgentView) -> CommunicationAction | None:
        self._mark("table talk", view)
        return self._inner.communicate(view)

    def update_beliefs(self, view: AgentView) -> dict[str, float] | None:
        self._mark("beliefs", view)
        return self._inner.update_beliefs(view)

    def act(self, view: AgentView) -> PokerAction:
        self._mark("action", view)
        return self._inner.act(view)


def default_seat_name(spec: str, i: int) -> str:
    if ":" in spec:
        model = spec.split(":", 1)[1].strip()
        return model[:20] or f"P{i + 1}"
    return f"{spec}-{i + 1}"


def build_seats(seats: list[dict], seed: int) -> list[Agent]:
    """Seat dicts ({spec, name?, api_key?}) → named, unique agents."""
    from bluffhouse.harness.cli import build_agent

    agents: list[Agent] = []
    used: set[str] = set()
    for i, seat in enumerate(seats):
        spec = seat["spec"].strip()
        name = (seat.get("name") or "").strip() or default_seat_name(spec, i)
        base, k = name, 2
        while name in used:
            name = f"{base}-{k}"
            k += 1
        used.add(name)
        agents.append(build_agent(spec, name, seed + i, api_key=seat.get("api_key") or None))
    return agents


def _partial_result(config: TableConfig, harness: GameHarness) -> GameResult:
    """A GameResult for a game stopped mid-flight: everything emitted so far.
    Stacks are as of the last completed hand — mid-hand chips stay unsettled."""
    stacks = {aid: config.starting_stack for aid in config.agent_ids}
    hands_played = 0
    for e in harness.log.events:
        if isinstance(e, HandEnded):
            stacks = dict(e.stacks)
            hands_played += 1
    return GameResult(
        config=config,
        final_stacks=stacks,
        hands_played=hands_played,
        log=harness.log,
        observations=harness.observations,
        llm_calls={
            aid: list(t)
            for aid, agent in harness.agents.items()
            if (t := getattr(agent, "transcript", None))
        },
        ledgers={aid: dict(led) for aid, led in harness.ledgers.items()},
    )


def start_live_game(
    root: Path, config: TableConfig, agents: list[Agent], run_name: str
) -> LiveJob:
    job = LiveJob(id=uuid.uuid4().hex[:10], config=config)
    watched = [_Watched(a, job) for a in agents]
    harness = GameHarness(config, watched)
    harness.log.subscribe(lambda ev: job.emit_event(ev.seq, ev.model_dump_json()))

    def run() -> None:
        try:
            result = harness.run()
            result.write(root / run_name)
            with job.lock:
                job.status, job.run_dir = "done", run_name
        except LiveStopped:
            # a stopped game still cost tokens and holds evidence — write
            # everything up to the stop point as a partial run
            partial = _partial_result(config, harness)
            partial.write(root / run_name)
            with job.lock:
                job.status, job.run_dir = "stopped", run_name
        except Exception as exc:  # noqa: BLE001 — surface anything to the UI
            with job.lock:
                job.status, job.error = "error", str(exc)
        finally:
            job.finish()

    job.thread = threading.Thread(target=run, daemon=True, name=f"live-{job.id}")
    job.thread.start()
    return job
