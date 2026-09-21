import pytest
from core.schemas import StudentProfile, SubjectProfile
from core.profiles.manager import ProfileManager

def test_profile_manager_student(tmp_path, monkeypatch):
    monkeypatch.setattr("core.profiles.manager.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("core.profiles.manager.STUDENT_PROFILE_PATH", tmp_path / "student_profile.json")
    
    manager = ProfileManager()
    assert manager.get_student_profile() is None
    
    profile = StudentProfile(
        student_name="Mohammad Taha",
        uid="24BCS12733",
        branch="BE-CSE",
        section_group="719-A",
        semester="5th",
        university="Chandigarh University"
    )
    manager.set_student_profile(profile)
    
    loaded = manager.get_student_profile()
    assert loaded is not None
    assert loaded.student_name == "Mohammad Taha"
    
def test_profile_manager_subjects(tmp_path, monkeypatch):
    monkeypatch.setattr("core.profiles.manager.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("core.profiles.manager.SUBJECTS_PATH", tmp_path / "subjects.json")
    
    manager = ProfileManager()
    assert manager.list_subjects() == []
    
    subject1 = SubjectProfile(
        subject_name="PBLJ",
        subject_code="24CSH-301",
        university="Chandigarh University",
        template_reference="templates/chandigarh-university/pblj/template.docx"
    )
    manager.add_subject(subject1)
    
    loaded = manager.get_subject("24CSH-301")
    assert loaded is not None
    assert loaded.subject_name == "PBLJ"
    
    assert len(manager.list_subjects()) == 1
