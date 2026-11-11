import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("STM_DATABASE", HERE / "student_tasks.sqlite3"))
SESSION_AGE = 7 * 24 * 60 * 60
COOKIE = "stm_session"


@contextmanager
def database():
    connection = sqlite3.connect(DATABASE, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@asynccontextmanager
async def lifespan(app):
    with database() as db:
        db.executescript((HERE / "schema.sql").read_text(encoding="utf-8"))
    yield


app = FastAPI(title="Student Task Manager", lifespan=lifespan)


@app.middleware("http")
async def guard_writes(request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.headers.get("x-stm-request") != "1":
            return JSONResponse({"detail": "Запит не підтверджено."}, status_code=403)
    return await call_next(request)


@app.exception_handler(sqlite3.Error)
async def database_error(request, exc):
    return JSONResponse({"detail": "База даних тимчасово недоступна."}, status_code=503)


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class Registration(Login):
    name: str = Field(max_length=80)
    confirmation: str = Field(max_length=128)


class TaskData(BaseModel):
    title: str = Field(max_length=120)
    description: str = Field(max_length=2000)
    due_date: date
    priority: int = Field(ge=1, le=3)
    category_id: int = Field(gt=0)


class TaskState(BaseModel):
    completed: bool


def derive(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=2**17, r=8, p=1, maxmem=256*1024**2)


def hash_password(password):
    salt = secrets.token_bytes(16)
    return salt.hex() + ":" + derive(password, salt).hex()


def matches(password, stored):
    salt, digest = stored.split(":")
    return hmac.compare_digest(derive(password, bytes.fromhex(salt)).hex(), digest)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def current_user(request: Request):
    token = request.cookies.get(COOKIE)
    if token:
        with database() as db:
            user = db.execute(
                "SELECT users.id, users.name FROM users JOIN sessions "
                "ON sessions.user_id = users.id WHERE token_hash = ? AND expires_at > ?",
                (token_hash(token), int(time.time())),
            ).fetchone()
            if user:
                return dict(user)
    raise HTTPException(401, "Спочатку увійдіть в обліковий запис.")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(HERE / "index.html")


@app.post("/api/register", status_code=201)
def register(data: Registration):
    name, email = data.name.strip(), data.email.strip().lower()
    if not name or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(422, "Укажіть ім’я та правильну електронну адресу.")
    if len(data.password) < 8 or data.password != data.confirmation:
        raise HTTPException(422, "Пароль має містити щонайменше 8 символів і збігатися з підтвердженням.")
    digest = hash_password(data.password)
    try:
        with database() as db:
            db.execute("INSERT INTO users(name, email, password_hash) VALUES (?, ?, ?)", (name, email, digest))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Цю електронну адресу вже зареєстровано.") from None
    return {"message": "Обліковий запис створено. Тепер увійдіть."}


@app.post("/api/login")
def login(data: Login, request: Request, response: Response):
    with database() as db:
        row = db.execute("SELECT * FROM users WHERE email = ?", (data.email.strip().lower(),)).fetchone()
    if not row or not matches(data.password, row["password_hash"]):
        raise HTTPException(401, "Неправильна електронна адреса або пароль.")
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with database() as db:
        db.execute("DELETE FROM sessions WHERE expires_at <= ?", (now,))
        old_token = request.cookies.get(COOKIE)
        if old_token:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(old_token),))
        db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash(token), row["id"], now + SESSION_AGE))
    response.set_cookie(COOKIE, token, max_age=SESSION_AGE, httponly=True,
                        secure=request.url.scheme == "https", samesite="lax")
    return {"id": row["id"], "name": row["name"]}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE)
    if token:
        with database() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(token),))
    response.delete_cookie(COOKIE)
    return {"message": "Ви вийшли з облікового запису."}


@app.get("/api/me")
def profile(user=Depends(current_user)):
    return user


@app.get("/api/categories")
def categories(user=Depends(current_user)):
    with database() as db:
        return [dict(row) for row in db.execute("SELECT * FROM categories ORDER BY id")]


def owned_task(db, task_id, user):
    row = db.execute("SELECT * FROM tasks WHERE id = ? AND owner_id = ?", (task_id, user["id"])).fetchone()
    if not row:
        raise HTTPException(404, "Завдання не знайдено.")
    return dict(row)


def task_values(db, data):
    title = data.title.strip()
    if not title:
        raise HTTPException(422, "Введіть назву завдання.")
    if not db.execute("SELECT id FROM categories WHERE id = ?", (data.category_id,)).fetchone():
        raise HTTPException(422, "Виберіть наявну категорію.")
    return title, data.description.strip(), data.due_date.isoformat(), data.priority, data.category_id


@app.get("/api/tasks")
def list_tasks(q: str = "", state: str = "all", category: int = 0,
               priority: int = 0, sort: str = "due", user=Depends(current_user)):
    if state not in ("all", "active", "completed") or sort not in ("due", "priority"):
        raise HTTPException(422, "Некоректні параметри перегляду.")
    if category < 0 or priority not in (0, 1, 2, 3):
        raise HTTPException(422, "Некоректні параметри фільтра.")
    order = {"due": "due_date ASC, priority DESC, id ASC",
             "priority": "priority DESC, due_date ASC, id ASC"}[sort]
    with database() as db:
        rows = db.execute(
            "SELECT * FROM tasks WHERE owner_id = ? "
            "AND (? = 'all' OR completed = ?) AND (? = 0 OR category_id = ?) "
            "AND (? = 0 OR priority = ?) ORDER BY " + order,
            (user["id"], state, int(state == "completed"), category, category, priority, priority),
        )
        needle = q.strip().casefold()
        return [dict(row) for row in rows if needle in row["title"].casefold()]


@app.get("/api/tasks/{task_id}")
def get_task(task_id: int, user=Depends(current_user)):
    with database() as db:
        return owned_task(db, task_id, user)


@app.post("/api/tasks", status_code=201)
def create_task(data: TaskData, user=Depends(current_user)):
    with database() as db:
        values = task_values(db, data)
        cursor = db.execute(
            "INSERT INTO tasks(title, description, due_date, priority, category_id, owner_id) VALUES (?, ?, ?, ?, ?, ?)",
            (*values, user["id"]),
        )
        return owned_task(db, cursor.lastrowid, user)


@app.put("/api/tasks/{task_id}")
def update_task(task_id: int, data: TaskData, user=Depends(current_user)):
    with database() as db:
        owned_task(db, task_id, user)
        values = task_values(db, data)
        db.execute(
            "UPDATE tasks SET title = ?, description = ?, due_date = ?, priority = ?, category_id = ? "
            "WHERE id = ? AND owner_id = ?", (*values, task_id, user["id"]),
        )
        return owned_task(db, task_id, user)


@app.patch("/api/tasks/{task_id}")
def set_state(task_id: int, data: TaskState, user=Depends(current_user)):
    with database() as db:
        db.execute("UPDATE tasks SET completed = ? WHERE id = ? AND owner_id = ?",
                   (int(data.completed), task_id, user["id"]))
        return owned_task(db, task_id, user)


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, user=Depends(current_user)):
    with database() as db:
        cursor = db.execute("DELETE FROM tasks WHERE id = ? AND owner_id = ?", (task_id, user["id"]))
        if cursor.rowcount != 1:
            raise HTTPException(404, "Завдання не знайдено.")
    return Response(status_code=204)
