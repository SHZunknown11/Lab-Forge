import os
import json
import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import Dict, Any, Optional

# JWT configuration
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", os.urandom(32).hex())
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

security = HTTPBearer()

class User(BaseModel):
    username: str
    role: str
    student_name: Optional[str] = None
    uid: Optional[str] = None
    batch: Optional[str] = None

class AuthManager:
    def __init__(self, users_file: Path = Path("config/users.json")):
        self.users_file = users_file
        self.users_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_users_file()

    def _ensure_users_file(self):
        if not self.users_file.exists():
            # Generate secure default passwords if file doesn't exist
            print("\n" + "="*50)
            print("INITIALIZING USERS DATABASE")
            admin_pwd = "admin"
            user1_pwd = "user1"
            print("Default Admin Password:", admin_pwd)
            print("Default User1 Password:", user1_pwd)
            print("PLEASE CHANGE THESE IN PRODUCTION!")
            print("="*50 + "\n")
            
            users_db = {
                "admin": {
                    "password_hash": self.get_password_hash(admin_pwd),
                    "role": "admin"
                },
                "user1": {
                    "password_hash": self.get_password_hash(user1_pwd),
                    "role": "user"
                }
            }
            self.users_file.write_text(json.dumps(users_db, indent=4))

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

    def get_password_hash(self, password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def register_user(self, username: str, password: str, student_name: str = None, uid: str = None, batch: str = None) -> User:
        users_db = json.loads(self.users_file.read_text())
        if username in users_db:
            raise ValueError("Username already exists")
        
        users_db[username] = {
            "password_hash": self.get_password_hash(password),
            "role": "user",
            "student_name": student_name,
            "uid": uid,
            "batch": batch
        }
        self.users_file.write_text(json.dumps(users_db, indent=4))
        return User(username=username, role="user", student_name=student_name, uid=uid, batch=batch)

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        if not self.users_file.exists():
            return None
        users_db = json.loads(self.users_file.read_text())
        user_record = users_db.get(username)
        if not user_record:
            return None
        if not self.verify_password(password, user_record["password_hash"]):
            return None
        return User(
            username=username, 
            role=user_record["role"],
            student_name=user_record.get("student_name"),
            uid=user_record.get("uid"),
            batch=user_record.get("batch")
        )

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    def get_current_user(self, credentials: HTTPAuthorizationCredentials = Security(security)) -> User:
        token = credentials.credentials
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            role: str = payload.get("role")
            if username is None or role is None:
                raise HTTPException(status_code=401, detail="Could not validate credentials")
            return User(username=username, role=role)
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Could not validate credentials")


class UsageTracker:
    def __init__(self, usage_file: Path = Path("config/usage.json")):
        self.usage_file = usage_file
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.usage_file.exists():
            self.usage_file.write_text(json.dumps({}))

    def _get_today_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def get_usage(self, username: str) -> int:
        data = json.loads(self.usage_file.read_text())
        user_data = data.get(username, {})
        today = self._get_today_str()
        
        if user_data.get("date") == today:
            return user_data.get("count", 0)
        return 0

    def increment_usage(self, username: str):
        data = json.loads(self.usage_file.read_text())
        today = self._get_today_str()
        
        user_data = data.get(username, {})
        if user_data.get("date") == today:
            user_data["count"] = user_data.get("count", 0) + 1
        else:
            user_data = {"date": today, "count": 1}
            
        data[username] = user_data
        self.usage_file.write_text(json.dumps(data, indent=4))

auth_manager = AuthManager()
usage_tracker = UsageTracker()
