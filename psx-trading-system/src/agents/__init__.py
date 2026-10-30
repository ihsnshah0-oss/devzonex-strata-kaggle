"""Background analysis agents — they start with the main system and keep the
deep-analysis caches warm so the Stocks tab & PDF open instantly."""
from src.agents.core import AGENTS, start_agents, agent_status  # noqa: F401
