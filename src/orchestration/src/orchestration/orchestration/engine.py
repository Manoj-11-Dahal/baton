"""Orchestration engine built on LangGraph.

Coordinates the Leader Agent and Sub-Agents. Supports:
- parallel and sequential agent execution
- task decomposition
- shared task context
- structured outputs
- retries, timeouts, model fallback (via the Leader)
- communication between Leader and Sub-Agents

The Leader Agent remains the single authority over model assignments.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph

from ..agents.leader import LeaderAgent, get_leader
from ..agents.sub_agents import build_all_sub_agents
from ..core.observability import get_observability
from ..core.security import make_default_security_context
from ..core.types import AgentResult, TaskRequest


@dataclass
class OrchestrationState:
    """Shared state flowing through the LangGraph."""
    user_request: str
    context: Dict[str, Any] = field(default_factory=dict)
    sequential: bool = False
    tasks: List[TaskRequest] = field(default_factory=list)
    results: List[AgentResult] = field(default_factory=list)
    final: Optional[AgentResult] = None
    error: Optional[str] = None
    started_at: float = field(default_factory=time.time)


class OrchestrationEngine:
    """LangGraph engine that wires Leader + Sub-Agents together."""

    def __init__(
        self,
        leader: Optional[LeaderAgent] = None,
        max_parallel_subagents: int = 5,
    ):
        self.leader = leader or LeaderAgent()
        self.max_parallel_subagents = max_parallel_subagents
        self.obs = get_observability()
        self._register_sub_agents()
        self.graph = self._build_graph()

    def _register_sub_agents(self) -> None:
        for agent in build_all_sub_agents().values():
            self.leader.register_sub_agent(agent)
        self.leader.max_parallel_subagents = self.max_parallel_subagents

    # ---------------------------------------------------------------- graph

    def _build_graph(self) -> StateGraph:
        graph = StateGraph(OrchestrationState)

        graph.add_node("analyze", self._analyze_node)
        graph.add_node("execute", self._execute_node)
        graph.add_node("review", self._review_node)
        graph.add_node("finalize", self._finalize_node)

        graph.set_entry_point("analyze")
        graph.add_edge("analyze", "execute")
        graph.add_edge("execute", "review")
        graph.add_edge("review", "finalize")
        graph.add_edge("finalize", END)

        return graph.compile()

    # ---------------------------------------------------------------- nodes

    async def _analyze_node(self, state: OrchestrationState) -> OrchestrationState:
        state.tasks = self.leader.analyze_request(state.user_request, state.context)
        return state

    async def _execute_node(self, state: OrchestrationState) -> OrchestrationState:
        if state.sequential or len(state.tasks) == 1:
            for task in state.tasks:
                agent_id = self.leader._select_agent_for(task)
                result = await self.leader.execute_sub_agent(agent_id, task)
                state.results.append(result)
        else:
            semaphore = asyncio.Semaphore(self.max_parallel_subagents)

            async def run_one(task: TaskRequest) -> AgentResult:
                async with semaphore:
                    agent_id = self.leader._select_agent_for(task)
                    return await self.leader.execute_sub_agent(agent_id, task)

            state.results = await asyncio.gather(*(run_one(t) for t in state.tasks))
        return state

    async def _review_node(self, state: OrchestrationState) -> OrchestrationState:
        if not state.results:
            state.error = "No results produced during execution."
            return state
        state.final = self.leader.resolve_conflicts(state.results)
        return state

    async def _finalize_node(self, state: OrchestrationState) -> OrchestrationState:
        elapsed_ms = int((time.time() - state.started_at) * 1000)
        if state.final:
            self.obs.record_agent_result(state.final)
        return state

    # ---------------------------------------------------------------- run

    async def run(
        self,
        user_request: str,
        context: Optional[Dict[str, Any]] = None,
        sequential: bool = False,
    ) -> Dict[str, Any]:
        initial = OrchestrationState(
            user_request=user_request,
            context=context or {},
            sequential=sequential,
        )
        with self.obs.span("orchestration.run", attributes={"user_request": user_request[:100]}):
            final_state = await self.graph.ainvoke(initial)
        # LangGraph ainvoke returns a plain dict; convert key fields safely.
        if isinstance(final_state, dict):
            tasks = final_state.get("tasks", [])
            results = final_state.get("results", [])
            final = final_state.get("final")
            error = final_state.get("error")
        else:
            tasks = final_state.tasks
            results = final_state.results
            final = final_state.final
            error = final_state.error
        return {
            "leader_agent": self.leader.agent_id,
            "user_request": user_request,
            "tasks": [t.model_dump() for t in tasks],
            "results": [r.model_dump() for r in results],
            "final": final.model_dump() if final else None,
            "error": error,
            "elapsed_ms": int((time.time() - initial.started_at) * 1000),
            "assignments": {
                aid: a.model_dump() for aid, a in self.leader.assignments.items()
            },
        }


_engine: Optional[OrchestrationEngine] = None


def get_engine() -> OrchestrationEngine:
    global _engine
    if _engine is None:
        _engine = OrchestrationEngine(leader=get_leader())
    return _engine
