from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JudgeStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


class StepStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


class JudgeResult(BaseModel):
    status: JudgeStatus
    reason: str


class PromptConfig(BaseModel):
    id: Optional[str] = None
    name: str
    json_path: str
    auto_delete: bool = Field(default=False, alias="auto-delete")
    update_if_exists: bool = Field(default=False, alias="update-if-exists")

    model_config = {"populate_by_name": True}


class GraphConfig(BaseModel):
    id: Optional[str] = None
    name: str
    file_path: str
    auto_delete: bool = Field(default=False, alias="auto-delete")
    update_if_exists: bool = Field(default=False, alias="update-if-exists")
    force_create: bool = Field(default=False, alias="force-create")

    model_config = {"populate_by_name": True}


class AppConfig(BaseModel):
    name: str
    auto_delete: bool = Field(default=False, alias="auto-delete")

    model_config = {"populate_by_name": True}


class AnswerJudge(BaseModel):
    questions: list[str]
    criteria: list[str]


class Scenario(BaseModel):
    scenario_name: str
    graph: GraphConfig
    app: Optional[AppConfig] = None
    prompts: list[PromptConfig] = Field(default_factory=list)
    answer_judge: Optional[AnswerJudge] = Field(default=None, alias="answer-judge")

    model_config = {"populate_by_name": True}


class StepResult(BaseModel):
    step: str
    status: StepStatus
    request: Optional[dict] = None
    response: Optional[str] = None
    elapsed_time: Optional[float] = None
    judge_result: Optional[JudgeResult] = None
    error: Optional[str] = None


class ScenarioResult(BaseModel):
    scenario_name: str
    steps: list[StepResult] = Field(default_factory=list)
    final_status: StepStatus = StepStatus.FAIL

    def compute_final_status(self) -> StepStatus:
        non_skip = [s for s in self.steps if s.status != StepStatus.SKIP]
        if not non_skip:
            self.final_status = StepStatus.PASS
        elif any(s.status == StepStatus.ERROR for s in non_skip):
            self.final_status = StepStatus.ERROR
        elif all(s.status == StepStatus.PASS for s in non_skip):
            self.final_status = StepStatus.PASS
        else:
            self.final_status = StepStatus.FAIL
        return self.final_status
