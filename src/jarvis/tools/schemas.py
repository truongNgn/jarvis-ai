from typing import Literal

from jarvis.contracts import StrictModel


class MetricsArgs(StrictModel):
    pass


class ProjectArgs(StrictModel):
    project_id: Literal["jarvis-ai"]


class MetricsData(StrictModel):
    cpu_percent: float
    ram_used_gib: float
    ram_total_gib: float
    source: Literal["fixture"] = "fixture"


class ProjectData(StrictModel):
    project_id: Literal["jarvis-ai"]
    editor: Literal["VS Code"] = "VS Code"
    opened: Literal[True] = True
    source: Literal["fixture"] = "fixture"


class BranchData(StrictModel):
    project_id: Literal["jarvis-ai"]
    branch: str
    source: Literal["fixture"] = "fixture"
