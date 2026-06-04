from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable


@runtime_checkable
class Agent(Protocol):
    name: str


TAgent = TypeVar("TAgent", bound=Agent)


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, name: str, agent: Agent) -> None:
        if name in self._agents:
            raise ValueError(f"Agent already registered: {name}")
        self._agents[name] = agent

    def resolve(self, name: str, expected_type: type[TAgent]) -> TAgent:
        try:
            agent = self._agents[name]
        except KeyError as exc:
            raise KeyError(f"Agent is not registered: {name}") from exc
        if not isinstance(agent, expected_type):
            raise TypeError(f"Agent '{name}' is not a {expected_type.__name__}.")
        return agent
