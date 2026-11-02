from core.activity import ActivityLog
from core.ingestion.header import read_header, strip_personal

SHEET = """DEPARTMENT OF CSE
Experiment 2.3
Student Name: Mohammad Taha
UID:24bcs12733
Branch: BE-CSE     Section/Group: 719(A)
Semester: 5th
Date: 16.07.26
Subject: Competitive Coding - II
Subject Code: 24CSP-305
1. Aim
Justify text.
name: kept"""


def test_sheet_header_fills_the_form_and_never_reaches_the_ai():
    assert read_header(SHEET) == {
        "Student Name": "Mohammad Taha", "UID": "24BCS12733", "Branch": "BE-CSE", "Section/Group": "719(A)",
        "Semester": "5th", "Date": "16.07.26", "Subject Name": "Competitive Coding - II", "Subject Code": "24CSP-305"}
    clean = strip_personal(SHEET)
    assert "Taha" not in clean and "24bcs" not in clean.lower() and "16.07.26" not in clean
    assert "Subject Code: 24CSP-305" in clean and clean.endswith("name: kept")
    # Two classmates' copies of one sheet become the same text, so they share a cache entry.
    other = SHEET.replace("Mohammad Taha", "Asha Rao").replace("24bcs12733", "24BCS99")
    assert strip_personal(other) == clean
    assert read_header("Aim: print hello") == {}


def test_reports_fold_reruns_downloads_and_feedback_into_one_entry(tmp_path):
    log = ActivityLog(db_url="", path=tmp_path / "a.jsonl")
    tasks = [{"title": "Easy", "language": "java", "status": "passed", "note": "", "output": "ok"},
             {"title": "Hard", "language": "java", "status": "not_run", "note": "Needs jakarta", "output": ""}]
    log.record("draft", "j1", name="", uid="", ip="1.2.3.4", title="Experiment 8", tasks=tasks, error="")
    log.record("run", "j1", index=1, status="passed", note="", output="done")
    log.record("render", "j1", name="Asha", uid="24BCS1", warnings=[], tasks=[])
    log.record("feedback", "j1", rating="down", reasons=["Wrong output"], comment="Hard is wrong")
    log.record("draft", "j2", name="Ravi", uid="", ip="5.6.7.8", title="Experiment 9", tasks=tasks[1:], error="")
    log.flush()

    reports = {r["job"]: r for r in log.reports(days=1)}
    one, two = reports["j1"], reports["j2"]
    assert (one["name"], one["uid"], one["ip"]) == ("Asha", "24BCS1", "1.2.3.4")
    assert [t["status"] for t in one["tasks"]] == ["passed", "passed"]
    assert one["reruns"] == 1 and one["downloads"] == 1
    assert one["feedback"]["rating"] == "down" and one["feedback"]["comment"] == "Hard is wrong"
    assert one["issue"]  # a thumbs down is an issue even when every program ran
    assert two["issue"] and two["tasks"][0]["note"] == "Needs jakarta" and two["feedback"] is None
