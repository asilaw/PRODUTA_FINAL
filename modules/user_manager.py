"""User management — simple JSON database for local DSS."""
import json
import hashlib
import time
import uuid
from pathlib import Path

USERS_FILE = Path("data/users.json")
SESSIONS_FILE = Path("data/sessions.json")
SESSION_TTL = 3600  # 1 hour in seconds

def _hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def load_users() -> dict:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text())
    # Default admin account
    defaults = {"admin": {"name":"Administrator","phone":"","password":_hash_pw("fbmi2026"),"role":"admin"}}
    USERS_FILE.write_text(json.dumps(defaults, indent=2))
    return defaults

def save_users(users: dict):
    USERS_FILE.write_text(json.dumps(users, indent=2))

def register(username: str, password: str, name: str, phone: str) -> tuple[bool, str]:
    users = load_users()
    if not username.strip(): return False, "Username tidak boleh kosong."
    if username in users: return False, "Username sudah dipakai."
    if len(password) < 6: return False, "Password minimal 6 karakter."
    users[username] = {"name": name, "phone": phone, "password": _hash_pw(password), "role": "user"}
    save_users(users)
    return True, "Akun berhasil dibuat."

def verify_login(username: str, password: str) -> tuple[bool, dict]:
    users = load_users()
    if username not in users: return False, {}
    u = users[username]
    if u["password"] == _hash_pw(password): return True, u
    return False, {}

def create_session(username: str) -> str:
    token = str(uuid.uuid4())
    sessions = {}
    if SESSIONS_FILE.exists():
        try: sessions = json.loads(SESSIONS_FILE.read_text())
        except: pass
    # Clean expired
    now = time.time()
    sessions = {k: v for k,v in sessions.items() if now - v["created"] < SESSION_TTL}
    sessions[token] = {"username": username, "created": now}
    SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSIONS_FILE.write_text(json.dumps(sessions))
    return token

def verify_session(token: str) -> tuple[bool, str]:
    if not token or not SESSIONS_FILE.exists(): return False, ""
    try:
        sessions = json.loads(SESSIONS_FILE.read_text())
        if token not in sessions: return False, ""
        s = sessions[token]
        if time.time() - s["created"] > SESSION_TTL:
            del sessions[token]
            SESSIONS_FILE.write_text(json.dumps(sessions))
            return False, ""
        return True, s["username"]
    except: return False, ""
