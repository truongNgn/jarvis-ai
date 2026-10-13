"""Immutable session grants supplied by trusted application code."""
from dataclasses import dataclass

TOOLS = frozenset({"system_metrics", "project_open", "git_branch"})


@dataclass(frozen=True)
class Grant:
    principal: str
    tools: frozenset[str]
    projects: frozenset[str]

    def allows(self, name: str, args: dict) -> bool:
        return (self.principal == "local-user" and name in TOOLS and name in self.tools
                and ("project_id" not in args or args["project_id"] in self.projects))


def demo_grant() -> Grant:
    return Grant("local-user", TOOLS, frozenset({"jarvis-ai"}))
