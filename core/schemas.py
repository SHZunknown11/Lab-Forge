"""Pydantic data models shared by the API, pipeline and CLI."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ── Stored defaults (CLI) ─────────────────────────────────────────

class StudentProfile(BaseModel):
    student_name: str
    uid: str
    branch: str
    section_group: str
    semester: str
    university: str


class SubjectProfile(BaseModel):
    subject_name: str
    subject_code: str
    university: str
    template_reference: str


# ── What the model writes ─────────────────────────────────────────
# Kept deliberately small: every field here is paid for in output tokens.

LANGUAGES = (
    "java", "python", "c", "cpp", "javascript", "react", "html", "matlab", "sql", "r", "shell", "other",
)


class AIFile(BaseModel):
    name: str
    code: str


class AITask(BaseModel):
    title: str
    problem: str
    objectives: list[str]
    language: str
    files: list[AIFile]
    stdin: str


class AIReport(BaseModel):
    experiment_no: str
    title: str
    aim: str
    tasks: list[AITask]
    learning_outcomes: list[str]


class AIFix(BaseModel):
    index: int
    files: list[AIFile]
    stdin: str


class AIFixes(BaseModel):
    fixes: list[AIFix]


class VivaQuestion(BaseModel):
    q: str
    a: str


class AIExplain(BaseModel):
    """What a student should be able to say about their program in a viva."""
    summary: str
    steps: list[str]
    viva: list[VivaQuestion]


# ── Draft the student reviews and edits ───────────────────────────

RunStatus = Literal["passed", "failed", "not_run"]


class CodeFile(BaseModel):
    name: str = Field(default="main", max_length=120)
    code: str = Field(default="", max_length=60_000)


class Task(BaseModel):
    title: str = ""
    problem: str = ""
    objectives: list[str] = Field(default_factory=list)
    language: str = "other"
    files: list[CodeFile] = Field(default_factory=list)
    stdin: str = ""
    # Filled only by the executor, never by the model.
    output: str = ""
    status: RunStatus = "not_run"
    note: str = ""
    # File names inside the job folder: captured figures and uploaded screenshots.
    images: list[str] = Field(default_factory=list)
    show_console: bool = True

    @field_validator("objectives", mode="before")
    @classmethod
    def _split_objectives(cls, v):
        if isinstance(v, str):
            return [line.strip(" •-*\t") for line in v.splitlines() if line.strip(" •-*\t")]
        return v


class ReportDraft(BaseModel):
    experiment_no: str = ""
    title: str = ""
    aim: str = ""
    tasks: list[Task] = Field(default_factory=list)
    learning_outcomes: list[str] = Field(default_factory=list)


class MetaField(BaseModel):
    label: str = Field(max_length=60)
    value: str = Field(default="", max_length=200)


class RenderRequest(BaseModel):
    draft: ReportDraft
    fields: list[MetaField] = Field(max_length=24)
    template: str = "cu-cse"
    pdf: bool = True
    sign_code: bool = False  # add "Name - UID" as a comment on top of each file


# ── Execution ─────────────────────────────────────────────────────

class RunResult(BaseModel):
    status: RunStatus
    output: str = ""
    note: str = ""
    figures: list[str] = Field(default_factory=list)  # absolute paths of produced images
    retryable: bool = False  # True when an AI fix could plausibly help


class ValidationResult(BaseModel):
    is_valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
