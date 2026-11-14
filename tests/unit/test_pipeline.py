"""The fix round: applying an AI fix must never drop a file the model didn't send back.

Found by running a real Spring Boot experiment sheet through LabForge with live AI calls. The
model wrote two files for the Easy task (CollegeApplication.java and StudentService.java) with a
misplaced bracket in the first. Asked to fix it, the model corrected the bracket and returned
only the file it had changed. The orchestrator replaced the task's whole file list with that
answer, deleting StudentService.java, so a good fix ended as "cannot find symbol: class
StudentService". Fixes are now merged by file name: see core/pipeline/orchestrator.py:_merge_fix.
"""
from core.ai.provider import DraftCache
from core.pipeline.orchestrator import _merge_fix, build_draft
from core.schemas import AIFile, AIFix, AIFixes, AIReport, AITask, CodeFile, RunResult

APP = "public class CollegeApplication { /* main; uses StudentService */ }"
APP_TYPO = "public class CollegeApplication { forEach((name, branch -> }"
SERVICE = "class StudentService { }"
SHEET = "Experiment 8. Easy: build a Spring Boot application with a StudentService bean and a runner."
BOTH = ["CollegeApplication.java", "StudentService.java"]


def cf(name, code="x"):
    return CodeFile(name=name, code=code)


def af(name, code):
    return AIFile(name=name, code=code)


# ── merging a fix into a task's files ──────────────────────────────

def test_a_fix_that_returns_only_the_file_it_changed_keeps_the_others():
    merged = _merge_fix([cf("CollegeApplication.java", APP_TYPO), cf("StudentService.java", SERVICE)],
                        [af("CollegeApplication.java", APP)])
    assert [(f.name, f.code) for f in merged] == [("CollegeApplication.java", APP), ("StudentService.java", SERVICE)]


def test_a_fix_that_only_adds_a_file_keeps_the_original_one():
    merged = _merge_fix([cf("CollegeApplication.java", APP)], [af("StudentService.java", SERVICE)])
    assert [(f.name, f.code) for f in merged] == [("CollegeApplication.java", APP), ("StudentService.java", SERVICE)]


def test_a_fix_with_no_name_is_still_appended():
    merged = _merge_fix([cf("a.py", "old")], [af("", "stray")])
    assert [(f.name, f.code) for f in merged] == [("a.py", "old"), ("", "stray")]


def test_a_fix_that_returns_every_file_is_a_plain_replace():
    merged = _merge_fix([cf("a.py", "old"), cf("b.py", "old")], [af("a.py", "new"), af("b.py", "new")])
    assert [(f.name, f.code) for f in merged] == [("a.py", "new"), ("b.py", "new")]


# ── the whole fix round ────────────────────────────────────────────

class FakeProvider:
    """Writes the Easy task as `first_files`, then answers the fix request with `fix_files`."""

    name = "fake"

    def __init__(self, first_files, fix_files):
        self.first_files, self.fix_files = first_files, fix_files

    def generate(self, sheet, language, subject, variant):
        return AIReport(experiment_no="8", title="Experiment 8", aim="Spring Core.", learning_outcomes=["Beans."],
                        tasks=[AITask(title="Easy Level", problem="Print students.", objectives=["DI"],
                                      language="java", files=self.first_files, stdin="")])

    def fix(self, items):
        assert [f["name"] for f in items[0]["files"]] == [f.name for f in self.first_files]
        return AIFixes(fixes=[AIFix(index=0, files=self.fix_files, stdin="")])


class FakeRunner:
    """Like javac: needs both classes, and no misplaced bracket."""

    def run(self, language, files, stdin, workdir):
        code = {f.name: f.code for f in files}
        if "StudentService.java" not in code:
            return RunResult(status="failed", retryable=True, note="The program didn't compile.",
                             output="error: cannot find symbol\n  symbol:   class StudentService")
        if code.get("CollegeApplication.java") != APP:
            return RunResult(status="failed", retryable=True, note="The program didn't compile.",
                             output="CollegeApplication.java:17: error: ')' expected")
        return RunResult(status="passed", output="Name: Asha | Branch: CSE")


def write(tmp_path, first_files, fix_files):
    cache = DraftCache(tmp_path / "cache")
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    events = list(build_draft(SHEET, job_dir, "auto", "PBLJ", provider=FakeProvider(first_files, fix_files),
                              cache=cache, runner=FakeRunner()))
    return events[-1]["draft"]["tasks"][0], cache.get(DraftCache.key(SHEET, "auto"))


def test_fix_that_returns_only_the_corrected_file_ends_with_a_working_program(tmp_path):
    # The case from the real sheet: two files, a bracket error in one, the fix sends back that one.
    task, cached = write(tmp_path, [af("CollegeApplication.java", APP_TYPO), af("StudentService.java", SERVICE)],
                         [af("CollegeApplication.java", APP)])
    assert task["status"] == "passed" and "Asha" in task["output"]
    assert [f["name"] for f in task["files"]] == BOTH
    # The next student with this sheet gets the fixed program straight from the cache.
    assert [(f.name, f.code) for f in cached.tasks[0].files] == [(BOTH[0], APP), (BOTH[1], SERVICE)]


def test_fix_that_adds_a_missing_file_ends_with_a_working_program(tmp_path):
    task, cached = write(tmp_path, [af("CollegeApplication.java", APP)], [af("StudentService.java", SERVICE)])
    assert task["status"] == "passed"
    assert [f["name"] for f in task["files"]] == BOTH and [f.name for f in cached.tasks[0].files] == BOTH


def test_fix_that_changes_nothing_leaves_the_program_as_it_was(tmp_path):
    task, cached = write(tmp_path, [af("CollegeApplication.java", APP)], [af("CollegeApplication.java", APP)])
    assert task["status"] == "failed" and task["note"] == "The program didn't compile."
    assert [f["name"] for f in task["files"]] == ["CollegeApplication.java"]
    assert [f.name for f in cached.tasks[0].files] == ["CollegeApplication.java"]
