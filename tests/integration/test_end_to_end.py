import pytest
import os
from pathlib import Path
from core.profiles.manager import ProfileManager
from core.schemas import StudentProfile, SubjectProfile
from core.pipeline.orchestrator import generate_report

def test_end_to_end_generation(tmp_path, monkeypatch):
    # Set config and artifacts to tmp_path
    monkeypatch.setattr("core.profiles.manager.CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr("core.profiles.manager.STUDENT_PROFILE_PATH", tmp_path / "config/student_profile.json")
    monkeypatch.setattr("core.profiles.manager.SUBJECTS_PATH", tmp_path / "config/subjects.json")
    
    # Set artifacts dir to tmp
    monkeypatch.setattr("core.pipeline.orchestrator.Path", lambda x: tmp_path / "artifacts" if x == "artifacts" else Path(x))
    
    # 1. Setup profile
    profile_mgr = ProfileManager()
    profile_mgr.set_student_profile(StudentProfile(
        student_name="Test Student",
        uid="12345",
        branch="CSE",
        section_group="A",
        semester="5",
        university="Test Univ"
    ))
    
    profile_mgr.add_subject(SubjectProfile(
        subject_name="Test Subject",
        subject_code="TEST-101",
        university="Test Univ",
        template_reference="templates/chandigarh-university/pblj/template.docx"
    ))
    
    # 2. Run generation
    source_path = "examples/source-notes.md"
    manifest = generate_report(source_path, "TEST-101")
    
    # 3. Assertions
    assert manifest.source_identifier == source_path
    assert manifest.validation_status.is_valid is True
    assert Path(manifest.docx_path).exists()
    
    # Check execution evidences
    assert "easy" in manifest.execution_evidences
    assert manifest.execution_evidences["easy"].success is True
    
    assert "medium" in manifest.execution_evidences
    assert manifest.execution_evidences["medium"].success is True
    
    assert "hard" in manifest.execution_evidences
    assert manifest.execution_evidences["hard"].success is True
    
    # Check screenshots
    assert "easy" in manifest.screenshot_artifacts
    assert Path(manifest.screenshot_artifacts["easy"].image_path).exists()
    
    assert "medium" in manifest.screenshot_artifacts
    assert Path(manifest.screenshot_artifacts["medium"].image_path).exists()
    
    assert "hard" in manifest.screenshot_artifacts
    assert Path(manifest.screenshot_artifacts["hard"].image_path).exists()
