from core.activity import ActivityLog, who_from_sheet


def test_name_and_uid_come_from_the_sheet_header():
    sheet = "DEPARTMENT OF CSE\nExperiment 2.3\nStudent Name: Mohammad Taha\nUID:24bcs12733\nBranch: BE-CSE\n1. Aim"
    assert who_from_sheet(sheet) == ("Mohammad Taha", "24BCS12733")
    assert who_from_sheet("Aim: print hello") == ("", "")


def test_reports_fold_reruns_and_downloads_into_one_entry(tmp_path):
    log = ActivityLog(db_url="", path=tmp_path / "a.jsonl")
    tasks = [{"title": "Easy", "language": "java", "status": "passed", "note": "", "output": "ok"},
             {"title": "Hard", "language": "java", "status": "not_run", "note": "Needs jakarta", "output": ""}]
    log.record("draft", "j1", name="", uid="", ip="1.2.3.4", title="Experiment 8", tasks=tasks, error="")
    log.record("run", "j1", index=1, status="passed", note="", output="done")
    log.record("render", "j1", name="Asha", uid="24BCS1", warnings=[], tasks=[])
    log.record("draft", "j2", name="Ravi", uid="", ip="5.6.7.8", title="Experiment 9", tasks=tasks[1:], error="")
    log.flush()

    reports = {r["job"]: r for r in log.reports(days=1)}
    one, two = reports["j1"], reports["j2"]
    assert (one["name"], one["uid"], one["ip"]) == ("Asha", "24BCS1", "1.2.3.4")
    assert [t["status"] for t in one["tasks"]] == ["passed", "passed"]
    assert one["reruns"] == 1 and one["downloads"] == 1 and not one["issue"]
    assert two["issue"] and two["tasks"][0]["note"] == "Needs jakarta"
