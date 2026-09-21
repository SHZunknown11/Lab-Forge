import os
import shutil
import tempfile
from pathlib import Path
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file

from typing import Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Any, Optional

from core.pipeline.orchestrator import generate_report
from core.profiles.manager import ProfileManager
from apps.api.logger import RequestLogger
from apps.api.auth import auth_manager, usage_tracker, User

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="LabForge API")

# Allow CORS for local React development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    remaining_generations: int = -1

class LoginRequest(BaseModel):
    username: str
    password: str

class SignupRequest(BaseModel):
    username: str
    password: str
    student_name: str
    uid: str
    batch: str

@app.post("/api/signup")
def signup(request: SignupRequest):
    try:
        user = auth_manager.register_user(
            username=request.username,
            password=request.password,
            student_name=request.student_name,
            uid=request.uid,
            batch=request.batch
        )
        return {"message": "User created successfully", "username": user.username}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/login")
def login(request: LoginRequest):
    user = auth_manager.authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    token = auth_manager.create_access_token({"sub": user.username, "role": user.role})
    remaining = -1
    if user.role != "admin":
        usage = usage_tracker.get_usage(user.username)
        remaining = max(0, 3 - usage)
        
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": user.username,
        "role": user.role,
        "remaining_generations": remaining
    }

@app.get("/api/profiles")
def get_profiles(current_user: User = Depends(auth_manager.get_current_user)):
    profile_mgr = ProfileManager()
    global_student = profile_mgr.get_student_profile()
    
    # Merge global profile with user-specific profile if available
    student_dict = global_student.model_dump() if global_student else {}
    if current_user.student_name:
        student_dict["student_name"] = current_user.student_name
    if current_user.uid:
        student_dict["uid"] = current_user.uid
    if current_user.batch:
        student_dict["section_group"] = current_user.batch
        
    # If no data exists at all, set to None so frontend knows
    if not student_dict:
        student_dict = None

    subjects = profile_mgr.list_subjects()
    
    remaining = -1
    if current_user.role != "admin":
        usage = usage_tracker.get_usage(current_user.username)
        remaining = max(0, 3 - usage)
        
    return {
        "student": student_dict,
        "subjects": [s.model_dump() for s in subjects],
        "user": {
            "username": current_user.username,
            "role": current_user.role,
            "remaining_generations": remaining
        }
    }

@app.post("/api/generate", response_model=GenerateResponse)
async def api_generate(
    file: UploadFile = File(...),
    subject_code: str = Form(...),
    force_refresh: bool = Form(False),
    student_name: str | None = Form(None),
    uid: str | None = Form(None),
    batch: str | None = Form(None),
    custom_subject_code: str | None = Form(None),
    custom_subject_name: str | None = Form(None),
    x_user_id: str | None = Header(None),
    current_user: User = Depends(auth_manager.get_current_user)
):
    if current_user.role != "admin":
        usage = usage_tracker.get_usage(current_user.username)
        if usage >= 3:
            raise HTTPException(status_code=403, detail="Daily generation limit (3) exceeded for your account.")
    try:
        # Save uploaded file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".md", mode="wb") as temp_file:
            shutil.copyfileobj(file.file, temp_file)
            temp_path = temp_file.name

        # Construct student override if provided
        student_override = None
        profile_mgr = ProfileManager()
        
        if student_name or uid or batch:
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

        # Construct subject override if provided
        subject_override = None
        if custom_subject_code or custom_subject_name:
            base_subject = profile_mgr.get_subject(subject_code)
            if base_subject:
                from core.schemas import SubjectProfile
                subject_override = SubjectProfile(
                    subject_code=custom_subject_code if custom_subject_code is not None else base_subject.subject_code,
                    subject_name=custom_subject_name if custom_subject_name is not None else base_subject.subject_name,
                    university=base_subject.university,
                    template_reference=base_subject.template_reference
                )

        # Run the orchestrator
        manifest = generate_report(
            temp_path, 
            subject_code, 
            force_refresh, 
            student_override=student_override,
            subject_override=subject_override
        )
        
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
            
        remaining = -1
        if current_user.role != "admin":
            usage_tracker.increment_usage(current_user.username)
            usage = usage_tracker.get_usage(current_user.username)
            remaining = max(0, 3 - usage)

        return GenerateResponse(
            manifest=manifest.model_dump(),
            docx_url=docx_url,
            pdf_url=pdf_url,
            remaining_generations=remaining
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
