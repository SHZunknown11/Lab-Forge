from dotenv import load_dotenv
load_dotenv()  # Load .env (GEMINI_API_KEY, AI_MODE, etc.) before any module imports

import argparse
import sys
import shutil
from pathlib import Path
from core.profiles.manager import ProfileManager
from core.schemas import StudentProfile, SubjectProfile
from core.pipeline.orchestrator import generate_report
from core.ingestion.parser import parse_source_file
from core.validation.validator import DocumentValidator


def main():
    parser = argparse.ArgumentParser(description="LabForge CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Profile commands
    profile_parser = subparsers.add_parser("profile")
    profile_sub = profile_parser.add_subparsers(dest="subcommand")
    profile_sub.add_parser("show")
    
    set_profile = profile_sub.add_parser("set")
    set_profile.add_argument("--name", required=True)
    set_profile.add_argument("--uid", required=True)
    set_profile.add_argument("--branch", required=True)
    set_profile.add_argument("--section", required=True)
    set_profile.add_argument("--semester", required=True)
    set_profile.add_argument("--university", required=True)

    # Subject commands
    subject_parser = subparsers.add_parser("subject")
    subject_sub = subject_parser.add_subparsers(dest="subcommand")
    subject_sub.add_parser("list")
    
    add_subject = subject_sub.add_parser("add")
    add_subject.add_argument("--name", required=True)
    add_subject.add_argument("--code", required=True)
    add_subject.add_argument("--university", required=True)
    add_subject.add_argument("--template", required=True)

    # Experiment inspect
    inspect_parser = subparsers.add_parser("experiment")
    inspect_sub = inspect_parser.add_subparsers(dest="subcommand")
    inspect_do = inspect_sub.add_parser("inspect")
    inspect_do.add_argument("source")

    # Generate
    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--source", required=True)
    generate_parser.add_argument("--subject", required=True)
    generate_parser.add_argument("--experiment", required=False) # extracted from source usually

    # Validate
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("docx")

    # Clean
    clean_parser = subparsers.add_parser("clean")

    args = parser.parse_args()
    
    profile_mgr = ProfileManager()

    if args.command == "profile":
        if args.subcommand == "show":
            profile = profile_mgr.get_student_profile()
            if profile:
                print(profile.model_dump_json(indent=2))
            else:
                print("No student profile configured.")
        elif args.subcommand == "set":
            profile = StudentProfile(
                student_name=args.name,
                uid=args.uid,
                branch=args.branch,
                section_group=args.section,
                semester=args.semester,
                university=args.university
            )
            profile_mgr.set_student_profile(profile)
            print("Student profile updated.")
            
    elif args.command == "subject":
        if args.subcommand == "list":
            subjects = profile_mgr.list_subjects()
            for s in subjects:
                print(f"{s.subject_code}: {s.subject_name} ({s.university}) - {s.template_reference}")
        elif args.subcommand == "add":
            subject = SubjectProfile(
                subject_name=args.name,
                subject_code=args.code,
                university=args.university,
                template_reference=args.template
            )
            profile_mgr.add_subject(subject)
            print(f"Subject {args.code} added.")
            
    elif args.command == "experiment":
        if args.subcommand == "inspect":
            doc = parse_source_file(args.source)
            print(doc.model_dump_json(indent=2))
            
    elif args.command == "generate":
        # Force refresh for testing if needed? Not exposed yet.
        generate_report(args.source, args.subject)
        
    elif args.command == "validate":
        validator = DocumentValidator()
        res = validator.validate(args.docx)
        print(f"Valid: {res.is_valid}")
        for err in res.errors:
            print(f"ERROR: {err}")
        for warn in res.warnings:
            print(f"WARN: {warn}")
            
    elif args.command == "clean":
        if Path("artifacts").exists():
            shutil.rmtree("artifacts")
            print("Cleaned artifacts.")
        else:
            print("No artifacts to clean.")

if __name__ == "__main__":
    main()
