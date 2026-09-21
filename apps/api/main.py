import os
import shutil
import tempfile
from pathlib import Path
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

from typing import Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.pipeline.orchestrator import generate_report
from core.profiles.manager import ProfileManager
from apps.api.logger import RequestLogger

app = FastAPI(title="LabForge API")
logger = RequestLogger()

# Ensure directories exist
artifacts_dir = Path("artifacts")
artifacts_dir.mkdir(exist_ok=True)
web_dir = Path("apps/web")
web_dir.mkdir(exist_ok=True, parents=True)

class GenerateResponse(BaseModel):
    manifest: Dict[str, Any]
    docx_url: str
    pdf_url: str | None = None

@app.get("/api/profiles")
def get_profiles():
    profile_mgr = ProfileManager()
    student = profile_mgr.get_student_profile()
    subjects = profile_mgr.list_subjects()
    return {
        "student": student.model_dump() if student else None,
        "subjects": [s.model_dump() for s in subjects]
    }

@app.post("/api/generate", response_model=GenerateResponse)
async def api_generate(
    file: UploadFile = File(...),
    subject_code: str = Form(...),
    force_refresh: bool = Form(False),
    student_name: str | None = Form(None),
    uid: str | None = Form(None),
    batch: str | None = Form(None),
    x_user_id: str | None = Header(None)
):
    try:
        # Save uploaded file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md", mode="wb") as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_path = temp_file.name

        # Construct student override if provided
        student_override = None
        if student_name or uid or batch:
            # Fallback to existing for other fields like university
            profile_mgr = ProfileManager()
            base_student = profile_mgr.get_student_profile()
            
            from core.schemas import StudentProfile
            student_override = StudentProfile(
                student_name=student_name if student_name is not None else (base_student.student_name if base_student else "Unknown"),
                uid=uid if uid is not None else (base_student.uid if base_student else "Unknown"),
                section_group=batch if batch is not None else (base_student.section_group if base_student else "Unknown"),
                branch=base_student.branch if base_student else "Unknown",
                semester=base_student.semester if base_student else "Unknown",
                university=base_student.university if base_student else "Unknown"
            )

        # Run the orchestrator
        manifest = generate_report(temp_path, subject_code, force_refresh, student_override=student_override)
        
        # Clean up temp file
        os.remove(temp_path)

        # Construct URLs for the generated files
        # manifest paths look like "artifacts/exp_3/Experiment_3_Report.docx"
        try:
            docx_rel = Path(manifest.docx_path).relative_to("artifacts").as_posix()
            docx_url = f"/api/artifacts/{docx_rel}"
        except ValueError:
            docx_url = f"/api/artifacts/{Path(manifest.docx_path).name}"

        pdf_url = None
        if manifest.pdf_path:
            try:
                pdf_rel = Path(manifest.pdf_path).relative_to("artifacts").as_posix()
                pdf_url = f"/api/artifacts/{pdf_rel}"
            except ValueError:
                pdf_url = f"/api/artifacts/{Path(manifest.pdf_path).name}"

        if x_user_id:
            logger.log_request(
                user_id=x_user_id,
                endpoint="/api/generate",
                status="SUCCESS",
                request_data={"subject_code": subject_code, "force_refresh": force_refresh}
            )
        return GenerateResponse(
            manifest=manifest.model_dump(),
            docx_url=docx_url,
            pdf_url=pdf_url
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        if x_user_id:
            logger.log_request(
                user_id=x_user_id,
                endpoint="/api/generate",
                status="ERROR",
                error_message=str(e),
                request_data={"subject_code": subject_code, "force_refresh": force_refresh}
            )
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs/{user_id}")
def get_user_logs(user_id: str):
    return logger.get_logs(user_id)

# Mount artifacts directory for downloading reports
app.mount("/api/artifacts", StaticFiles(directory="artifacts"), name="artifacts")

# Mount frontend
app.mount("/", StaticFiles(directory="apps/web", html=True), name="web")
