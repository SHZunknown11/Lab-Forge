"""Pydantic data models for the entire LabForge pipeline."""
from __future__ import annotations

from typing import Optional, Union
from pydantic import BaseModel, Field


# ── Student & Subject ──────────────────────────────────────────────

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


# ── Experiment source ──────────────────────────────────────────────

class ExperimentMetadata(BaseModel):
    experiment_number: str
    title: str
    aim: str = ""
    co_mapping: str = ""


class ExperimentLevel(BaseModel):
    problem_statement: str = ""
    objectives: str = ""
    code: str = ""
    filename: str = ""


class ExperimentDocument(BaseModel):
    metadata: ExperimentMetadata
    easy: Optional[ExperimentLevel] = None
    medium: Optional[ExperimentLevel] = None
    hard: Optional[ExperimentLevel] = None
    objectives: str = ""
    apparatus: str = ""
    reading_material: str = ""


# ── AI‑generated content ──────────────────────────────────────────

from pydantic import BaseModel, Field, field_validator

class GeneratedLevel(BaseModel):
    problem_statement: str = ""
    objectives: str = ""
    filename: str = ""
    code: str = ""
    expected_behavior: str = ""

    @field_validator("objectives", mode="before")
    def validate_objectives(cls, v):
        if isinstance(v, list):
            return "\n".join(str(item) for item in v)
        return v


class GeneratedContent(BaseModel):
    experiment_number: Union[str, int] = ""
    title: str = ""
    global_aim: str = ""
    easy: Optional[GeneratedLevel] = None
    medium: Optional[GeneratedLevel] = None
    hard: Optional[GeneratedLevel] = None
    learning_outcomes: list[str] = Field(default_factory=list)


# ── Execution evidence ────────────────────────────────────────────

class ExecutionResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: int = 0


class ExecutionEvidence(BaseModel):
    level: str
    source_code: str
    compilation_result: ExecutionResult
    execution_result: Optional[ExecutionResult] = None
    success: bool = False


# ── Screenshots ───────────────────────────────────────────────────

class ScreenshotArtifact(BaseModel):
    level: str
    image_path: str
    width: int = 0
    height: int = 0


# ── Validation ────────────────────────────────────────────────────

class ValidationResult(BaseModel):
    is_valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ── Report manifest ──────────────────────────────────────────────

class ReportManifest(BaseModel):
    source_identifier: str = ""
    subject_code: str = ""
    docx_path: str = ""
    pdf_path: Optional[str] = None
    execution_evidences: dict[str, ExecutionEvidence] = Field(default_factory=dict)
    screenshot_artifacts: dict[str, ScreenshotArtifact] = Field(default_factory=dict)
    validation_status: ValidationResult = Field(default_factory=ValidationResult)
