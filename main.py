"""LabForge command line.

    labforge generate --source sheet.pdf --subject "Competitive Coding-II" --code 24CSP-305
    labforge batch --dir "C:/Users/me/Desktop/cc sem5"     # every sheet in a folder
    labforge profile set --name "..." --uid ... --branch BE-CSE --section 719-A --semester 5th --university CU
    labforge doctor                                          # what can run on this machine
"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

import argparse  # noqa: E402
import shutil  # noqa: E402
import sys  # noqa: E402
from datetime import date  # noqa: E402
from pathlib import Path  # noqa: E402

from core.ai.provider import AIError, get_provider  # noqa: E402
from core.documents.pdf_converter import PdfConverter  # noqa: E402
from core.execution.runner import CodeRunner  # noqa: E402
from core.ingestion.extract import ACCEPTED_SUFFIXES, UnsupportedFile, condense, extract_text  # noqa: E402
from core.pipeline.orchestrator import build_draft, new_job, render_report  # noqa: E402
from core.profiles.manager import ProfileManager  # noqa: E402
from core.schemas import MetaField, RenderRequest, ReportDraft, StudentProfile, SubjectProfile  # noqa: E402
from core.validation.validator import DocumentValidator  # noqa: E402

SHEET_SUFFIXES = {".pdf", ".docx", ".pptx", ".txt", ".md", ".zip"}


def generate(source: Path, subject: str, code: str, language: str, template: str,
             out_dir: Path | None, fresh: bool, sign: bool) -> Path | None:
    profiles = ProfileManager()
    student = profiles.get_student_profile()
    if student is None:
        sys.exit("No profile yet. Run: labforge profile set --name ... --uid ... (see --help)")
    if not code:
        match = next((s for s in profiles.list_subjects() if s.subject_name.lower() == subject.lower()), None)
        code = match.subject_code if match else ""

    try:
        sheet = condense(extract_text(source.read_bytes(), source.name))
    except UnsupportedFile as exc:
        print(f"  skipped: {exc}")
        return None

    job_id, job_dir = new_job()
    draft = None
    try:
        for event in build_draft(sheet, job_dir, language, subject, fresh):
            if event["type"] == "stage":
                print(f"  {event['text']}")
            elif event["type"] == "task":
                print(f"    {event['title']}: {event['status']} {event['note']}".rstrip())
            elif event["type"] == "done":
                draft = ReportDraft.model_validate(event["draft"])
    except AIError as exc:
        print(f"  failed: {exc}")
        return None

    fields = [
        MetaField(label="Student Name", value=student.student_name),
        MetaField(label="UID", value=student.uid),
        MetaField(label="Branch", value=student.branch),
        MetaField(label="Section/Group", value=student.section_group),
        MetaField(label="Semester", value=student.semester),
        MetaField(label="Date", value=date.today().strftime("%d/%m/%Y")),
        MetaField(label="Subject Name", value=subject),
        MetaField(label="Subject Code", value=code),
    ]
    result = render_report(job_dir, RenderRequest(draft=draft, fields=fields, template=template, sign_code=sign))
    target_dir = out_dir or source.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    produced = job_dir / result["render"]
    saved = None
    for key in ("docx", "pdf"):
        if result.get(key):
            saved = target_dir / result[key]
            shutil.copy(produced / result[key], saved)
            print(f"  saved {saved}")
    for warning in result["warnings"]:
        print(f"  note: {warning}")
    return saved


def doctor() -> None:
    runner = CodeRunner()
    provider = get_provider()
    print("Programs that run here:")
    for lang, ok in sorted(runner.available().items()):
        print(f"  {'yes' if ok else 'no ':3}  {lang}")
    print("AI providers:", ", ".join(provider.describe()) or "none configured (set GEMINI_API_KEY or another key)")
    print("PDF export:", "yes" if PdfConverter().available() else "no (install LibreOffice or set GOTENBERG_URL)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="labforge", description="Lab reports from experiment sheets.")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="write one report")
    g.add_argument("--source", required=True, type=Path)
    b = sub.add_parser("batch", help="write a report for every sheet in a folder (recursively)")
    b.add_argument("--dir", required=True, type=Path)
    b.add_argument("--skip-existing", action="store_true", help="skip sheets that already have a report next to them")
    for p in (g, b):
        p.add_argument("--subject", default="")
        p.add_argument("--code", default="")
        p.add_argument("--language", default="auto")
        p.add_argument("--template", default="cu-cse", choices=["cu-cse", "plain"])
        p.add_argument("--out", type=Path, default=None)
        p.add_argument("--fresh", action="store_true", help="ignore the cache and write a new version")
        p.add_argument("--sign", action="store_true", help="put your name and UID as a comment in the code")

    prof = sub.add_parser("profile")
    prof_sub = prof.add_subparsers(dest="sub", required=True)
    prof_sub.add_parser("show")
    ps = prof_sub.add_parser("set")
    for name in ("name", "uid", "branch", "section", "semester", "university"):
        ps.add_argument(f"--{name}", required=True)

    subj = sub.add_parser("subject")
    subj_sub = subj.add_subparsers(dest="sub", required=True)
    subj_sub.add_parser("list")
    sa = subj_sub.add_parser("add")
    sa.add_argument("--name", required=True)
    sa.add_argument("--code", required=True)
    sa.add_argument("--university", default="")

    v = sub.add_parser("validate")
    v.add_argument("docx")
    sub.add_parser("doctor")
    sub.add_parser("clean", help="delete generated jobs and cached drafts")

    args = parser.parse_args()
    profiles = ProfileManager()

    if args.command == "generate":
        print(f"{args.source.name}")
        generate(args.source, args.subject, args.code, args.language, args.template, args.out, args.fresh, args.sign)
    elif args.command == "batch":
        sheets = sorted(p for p in args.dir.rglob("*") if p.suffix.lower() in SHEET_SUFFIXES
                        and p.suffix.lower() in ACCEPTED_SUFFIXES and "_Report" not in p.stem
                        and not p.stem.startswith("Experiment_"))
        print(f"{len(sheets)} sheets in {args.dir}")
        for sheet in sheets:
            if args.skip_existing and any(sheet.parent.glob("Experiment_*.docx")):
                continue
            print(f"\n{sheet.relative_to(args.dir)}")
            generate(sheet, args.subject, args.code, args.language, args.template, args.out, args.fresh, args.sign)
    elif args.command == "profile":
        if args.sub == "show":
            p = profiles.get_student_profile()
            print(p.model_dump_json(indent=2) if p else "No profile yet.")
        else:
            profiles.set_student_profile(StudentProfile(
                student_name=args.name, uid=args.uid, branch=args.branch, section_group=args.section,
                semester=args.semester, university=args.university))
            print("Profile saved.")
    elif args.command == "subject":
        if args.sub == "list":
            for s in profiles.list_subjects():
                print(f"{s.subject_code}  {s.subject_name}")
        else:
            profiles.add_subject(SubjectProfile(subject_name=args.name, subject_code=args.code,
                                                university=args.university, template_reference=""))
            print(f"Saved {args.code}.")
    elif args.command == "validate":
        res = DocumentValidator().validate(args.docx)
        print("Valid" if res.is_valid else "Invalid")
        for msg in res.errors + res.warnings:
            print(f"  {msg}")
    elif args.command == "doctor":
        doctor()
    elif args.command == "clean":
        for path in (Path("artifacts/jobs"), Path("artifacts/cache")):
            shutil.rmtree(path, ignore_errors=True)
        print("Removed generated jobs and cached drafts.")


if __name__ == "__main__":
    main()
