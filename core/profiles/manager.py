"""JSON-based persistent storage for student profile and subjects."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from core.schemas import StudentProfile, SubjectProfile

CONFIG_DIR = Path("config")
STUDENT_PROFILE_PATH = CONFIG_DIR / "student_profile.json"
SUBJECTS_PATH = CONFIG_DIR / "subjects.json"


class ProfileManager:
    """Manage student profile and subject configurations."""

    def get_student_profile(self) -> Optional[StudentProfile]:
        if not STUDENT_PROFILE_PATH.exists():
            return None
        data = json.loads(STUDENT_PROFILE_PATH.read_text(encoding="utf-8"))
        return StudentProfile(**data)

    def set_student_profile(self, profile: StudentProfile) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        STUDENT_PROFILE_PATH.write_text(
            profile.model_dump_json(indent=2), encoding="utf-8"
        )

    def list_subjects(self) -> list[SubjectProfile]:
        if not SUBJECTS_PATH.exists():
            return []
        data = json.loads(SUBJECTS_PATH.read_text(encoding="utf-8"))
        return [SubjectProfile(**s) for s in data]

    def add_subject(self, subject: SubjectProfile) -> None:
        subjects = self.list_subjects()
        # Replace existing subject with same code
        subjects = [s for s in subjects if s.subject_code != subject.subject_code]
        subjects.append(subject)
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SUBJECTS_PATH.write_text(
            json.dumps([s.model_dump() for s in subjects], indent=2),
            encoding="utf-8",
        )

    def get_subject(self, subject_code: str) -> Optional[SubjectProfile]:
        for s in self.list_subjects():
            if s.subject_code == subject_code:
                return s
        return None
