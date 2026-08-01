from __future__ import annotations

import io
import qrcode
import qrcode.image.svg

import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Blueprint, Flask, abort, flash, g, redirect, render_template, request, session, url_for, current_app, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

LFA_DIR = Path(__file__).resolve().parent
APP_ROOT = LFA_DIR.parent
DEFAULT_DB_PATH = APP_ROOT / "data" / "lfa" / "portal.sqlite3"
DEFAULT_DB = Path(os.environ.get("LFA_DATABASE", str(DEFAULT_DB_PATH)))

RA_RE = re.compile(r"^[A-Z0-9._ /-]{1,50}$")
CLASS_RE = re.compile(r"^[A-Z0-9._ /-]{1,50}$")

lfa_bp = Blueprint("lfa", __name__, template_folder="templates", static_folder="static", url_prefix="/lfa")


def get_lfa_db() -> sqlite3.Connection:
    if "lfa_db" not in g:
        db_path = DEFAULT_DB
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        conn = sqlite3.connect(db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 5000")
        except Exception:
            pass
        ensure_schema(conn)
        g.lfa_db = conn
    return g.lfa_db


@lfa_bp.teardown_app_request
def close_lfa_db(_: object | None = None) -> None:
    db = g.pop("lfa_db", None)
    if db is not None:
        db.close()


def query_all(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    return get_lfa_db().execute(sql, params).fetchall()


def query_one(sql: str, params: tuple = ()) -> sqlite3.Row | None:
    return get_lfa_db().execute(sql, params).fetchone()


def execute(sql: str, params: tuple = ()) -> None:
    db = get_lfa_db()
    db.execute(sql, params)
    db.commit()


def ensure_schema(conn: sqlite3.Connection) -> None:
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    except Exception:
        pass
    # Auto-migration for first_access column if table existed previously
    try:
        conn.execute("ALTER TABLE users ADD COLUMN first_access INTEGER NOT NULL DEFAULT 1")
        conn.commit()
    except Exception:
        pass
    # Auto-seed default professor if no professor exists
    try:
        cur = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'professor'")
        row = cur.fetchone()
        if not row or row["cnt"] == 0:
            prof_email = os.environ.get("LFA_PROF_EMAIL", "souzapeus@gmail.com")
            prof_name = os.environ.get("LFA_PROF_NAME", "Professor Pedro Souza")
            prof_pass = os.environ.get("LFA_PROF_PASSWORD", "ProfLFA2026!")
            conn.execute(
                "INSERT INTO users (role, name, email, password_hash, first_access, created_at) VALUES ('professor', ?, ?, ?, 0, ?)",
                (prof_name, prof_email.lower(), generate_password_hash(prof_pass), now_iso()),
            )
            conn.commit()
    except Exception as e:
        print(f"Warning: Failed to seed default professor: {e}")


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf() -> None:
    if request.method == "POST" and request.form.get("csrf_token") != session.get("csrf_token"):
        abort(400, "CSRF token inválido")


def lfa_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("lfa_user") is None:
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("lfa.login"))
        return view(*args, **kwargs)
    return wrapped


def lfa_role_required(role: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = g.get("lfa_user")
            if user is None:
                return redirect(url_for("lfa.login"))
            if user["role"] != role:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def normalize_ra(value: str) -> str:
    return value.strip().upper()


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@lfa_bp.before_app_request
def load_lfa_user():
    g.lfa_user = None
    user_id = session.get("lfa_user_id")
    if user_id:
        g.lfa_user = query_one("SELECT * FROM users WHERE id = ? AND active = 1", (user_id,))
    token_arg = request.args.get("token", "").strip().upper()
    if token_arg:
        session["pending_attendance_token"] = token_arg


@lfa_bp.app_template_global("lfa_csrf_token")
def lfa_csrf_token_global():
    return csrf_token()


@lfa_bp.route("/")
def index():
    materials = query_all("SELECT title, url, created_at FROM materials ORDER BY created_at DESC LIMIT 6")
    return render_template("lfa_index.html", materials=materials, current_user=g.lfa_user)


@lfa_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        validate_csrf()
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        norm_id = normalize_ra(identifier)
        clean_id = re.sub(r"[^A-Z0-9]", "", norm_id)
        user = query_one(
            """
            SELECT * FROM users 
            WHERE active = 1 AND (
                email = ? 
                OR ra = ? 
                OR (ra IS NOT NULL AND REPLACE(REPLACE(REPLACE(REPLACE(ra, '-', ''), '.', ''), ' ', ''), '/', '') = ?)
            )
            """,
            (identifier.lower(), norm_id, clean_id if clean_id else norm_id)
        )
        if user:
            u_dict = dict(user)
            first_acc = u_dict.get("first_access", 1)
            pass_hash = u_dict.get("password_hash")
            if user["role"] == "student" and (first_acc == 1 or not pass_hash or pass_hash == ""):
                flash("Este é o seu primeiro acesso. Por favor, cadastre sua senha.", "info")
                return redirect(url_for("lfa.primeiro_acesso", ra=user["ra"]))
            if pass_hash and check_password_hash(pass_hash, password):
                session.clear()
                session.permanent = True
                session["lfa_user_id"] = user["id"]
                session["csrf_token"] = secrets.token_urlsafe(32)
                flash("Login realizado com sucesso.", "success")
                return redirect(url_for("lfa.professor") if user["role"] == "professor" else url_for("lfa.student"))
        flash("Credenciais inválidas.", "error")
    return render_template("lfa_login.html", current_user=g.lfa_user)


@lfa_bp.route("/primeiro-acesso", methods=["GET", "POST"])
def primeiro_acesso():
    ra_param = request.args.get("ra", "").strip().upper()
    if request.method == "POST":
        validate_csrf()
        ra_raw = request.form.get("ra", "").strip()
        ra = normalize_ra(ra_raw)
        clean_ra = re.sub(r"[^A-Z0-9]", "", ra)
        password = request.form.get("password", "")
        password_confirm = request.form.get("password_confirm", "")

        if not ra or not RA_RE.match(ra):
            flash("Formato de RA inválido.", "error")
            return render_template("lfa_primeiro_acesso.html", ra=ra_raw, current_user=g.lfa_user)

        user = query_one(
            """
            SELECT * FROM users 
            WHERE role = 'student' AND active = 1 AND (
                ra = ? 
                OR (ra IS NOT NULL AND REPLACE(REPLACE(REPLACE(REPLACE(ra, '-', ''), '.', ''), ' ', ''), '/', '') = ?)
            )
            """,
            (ra, clean_ra if clean_ra else ra)
        )
        if not user:
            flash("RA não encontrado nas turmas cadastradas. Verifique com seu professor.", "error")
            return render_template("lfa_primeiro_acesso.html", ra=ra, current_user=g.lfa_user)

        u_dict = dict(user)
        if u_dict.get("first_access") == 0 and u_dict.get("password_hash") and u_dict.get("password_hash") != "":
            flash("Sua senha já foi cadastrada anteriormente. Faça login normalmente.", "info")
            return redirect(url_for("lfa.login"))

        if len(password) < 8:
            flash("A senha deve ter no mínimo 8 caracteres.", "error")
            return render_template("lfa_primeiro_acesso.html", ra=ra, current_user=g.lfa_user)

        if password != password_confirm:
            flash("A confirmação de senha não confere.", "error")
            return render_template("lfa_primeiro_acesso.html", ra=ra, current_user=g.lfa_user)

        execute(
            "UPDATE users SET password_hash = ?, first_access = 0 WHERE id = ?",
            (generate_password_hash(password), user["id"]),
        )
        session.clear()
        session.permanent = True
        session["lfa_user_id"] = user["id"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        flash("Senha cadastrada com sucesso! Bem-vindo(a) ao Portal LFA.", "success")
        return redirect(url_for("lfa.student"))

    return render_template("lfa_primeiro_acesso.html", ra=ra_param, current_user=g.lfa_user)


@lfa_bp.route("/logout", methods=["POST"])
@lfa_login_required
def logout():
    validate_csrf()
    session.clear()
    flash("Sessão encerrada.", "success")
    return redirect(url_for("lfa.index"))


@lfa_bp.route("/aluno", methods=["GET", "POST"])
@lfa_role_required("student")
def student():
    token_param = request.args.get("token", "").strip().upper() or session.pop("pending_attendance_token", None)
    if request.method == "POST":
        validate_csrf()
        token = request.form.get("attendance_token", "").strip().upper()
        record_attendance(token)
        return redirect(url_for("lfa.student"))
    if token_param and request.method == "GET":
        sess = query_one("SELECT * FROM attendance_sessions WHERE token = ?", (token_param,))
        if sess:
            already = query_one("SELECT id FROM attendance_records WHERE session_id = ? AND user_id = ?", (sess["id"], g.lfa_user["id"]))
            if not already:
                record_attendance(token_param)
                return redirect(url_for("lfa.student"))
    user = g.lfa_user
    grades = query_one("SELECT * FROM grades WHERE user_id = ?", (user["id"],))
    materials = query_all("SELECT * FROM materials ORDER BY created_at DESC")
    attendance = query_all("""
        SELECT s.topic, s.class_code, s.expires_at, r.created_at
        FROM attendance_records r
        JOIN attendance_sessions s ON s.id = r.session_id
        WHERE r.user_id = ?
        ORDER BY r.created_at DESC
    """, (user["id"],))
    ranking = query_all("SELECT name, class_code, xp FROM users WHERE role = 'student' AND active = 1 ORDER BY xp DESC, name ASC LIMIT 10")
    return render_template("lfa_student.html", grades=grades, materials=materials, attendance=attendance, ranking=ranking, current_user=user, initial_token=token_param or "")


@lfa_bp.route("/professor", methods=["GET"])
@lfa_role_required("professor")
def professor():
    students = query_all("SELECT u.*, g.np1, g.np2, g.nt, g.exam FROM users u LEFT JOIN grades g ON g.user_id = u.id WHERE u.role='student' ORDER BY u.class_code, u.name")
    materials = query_all("SELECT * FROM materials ORDER BY created_at DESC")
    sessions = query_all("""
        SELECT s.*, 
               (SELECT COUNT(*) FROM attendance_records r WHERE r.session_id = s.id) as present_count,
               (SELECT COUNT(*) FROM users u WHERE u.role = 'student' AND u.class_code = s.class_code) as total_students
        FROM attendance_sessions s 
        ORDER BY s.created_at DESC LIMIT 15
    """)
    return render_template("lfa_professor.html", students=students, materials=materials, sessions=sessions, current_user=g.lfa_user)


@lfa_bp.route("/professor/alunos", methods=["POST"])
@lfa_role_required("professor")
def add_student():
    validate_csrf()
    name = request.form.get("name", "").strip()
    ra = normalize_ra(request.form.get("ra", ""))
    class_code = request.form.get("class_code", "").strip().upper()
    temp_password = request.form.get("password", "").strip()
    if len(name) < 2 or not ra or not RA_RE.match(ra) or not CLASS_RE.match(class_code):
        flash("Dados inválidos. Verifique se Nome, RA e Turma foram preenchidos.", "error")
        return redirect(url_for("lfa.professor"))
    pass_hash = generate_password_hash(temp_password) if temp_password else ""
    first_acc = 0 if temp_password else 1
    try:
        db = get_lfa_db()
        cur = db.execute(
            "INSERT INTO users (role, name, ra, class_code, password_hash, first_access, created_at) VALUES ('student', ?, ?, ?, ?, ?, ?)",
            (name, ra, class_code, pass_hash, first_acc, now_iso()),
        )
        db.execute("INSERT INTO grades (user_id) VALUES (?)", (cur.lastrowid,))
        db.commit()
        flash(f"Aluno {name} ({ra}) cadastrado com sucesso.", "success")
    except sqlite3.IntegrityError as e:
        if "ra" in str(e).lower():
            flash("RA já cadastrado.", "error")
        else:
            flash(f"Erro ao cadastrar aluno: {e}", "error")
    return redirect(url_for("lfa.professor"))


@lfa_bp.route("/professor/materiais", methods=["POST"])
@lfa_role_required("professor")
def add_material():
    validate_csrf()
    title = request.form.get("title", "").strip()
    url = request.form.get("url", "").strip()
    if len(title) < 3 or not valid_url(url):
        flash("Informe título e URL http/https válidos.", "error")
    else:
        execute("INSERT INTO materials (title, url, created_by, created_at) VALUES (?, ?, ?, ?)", (title, url, g.lfa_user["id"], now_iso()))
        flash("Material publicado.", "success")
    return redirect(url_for("lfa.professor"))


@lfa_bp.route("/professor/notas", methods=["POST"])
@lfa_role_required("professor")
def update_grades():
    validate_csrf()
    user_id = int(request.form.get("user_id", "0"))
    if not query_one("SELECT id FROM users WHERE id = ? AND role = 'student'", (user_id,)):
        abort(404)
    values = tuple(parse_grade(request.form.get(field)) for field in ["np1", "np2", "nt", "exam"])
    execute("""
        INSERT INTO grades (user_id, np1, np2, nt, exam) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET np1=excluded.np1, np2=excluded.np2, nt=excluded.nt, exam=excluded.exam
    """, (user_id, *values))
    flash("Notas atualizadas.", "success")
    return redirect(url_for("lfa.professor"))


@lfa_bp.route("/professor/chamada", methods=["POST"])
@lfa_role_required("professor")
def create_attendance():
    validate_csrf()
    topic = request.form.get("topic", "").strip()[:120]
    class_code = request.form.get("class_code", "").strip().upper()
    minutes = max(5, min(int(request.form.get("minutes", "15") or 15), 180))
    if len(topic) < 3 or not CLASS_RE.match(class_code):
        flash("Informe tópico e turma válidos.", "error")
        return redirect(url_for("lfa.professor"))
    token = secrets.token_urlsafe(16).replace("-", "").replace("_", "")[:12].upper()
    expires = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    execute("INSERT INTO attendance_sessions (token, topic, class_code, expires_at, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)", (token, topic, class_code, expires.isoformat(), g.lfa_user["id"], now_iso()))
    flash(f"Chamada criada. Código: {token}", "success")
    return redirect(url_for("lfa.professor"))


def record_attendance(token: str) -> None:
    sess = query_one("SELECT * FROM attendance_sessions WHERE token = ?", (token,))
    if not sess:
        flash("Código de chamada inválido.", "error")
        return
    if datetime.fromisoformat(sess["expires_at"]) < datetime.now(timezone.utc):
        flash("Código de chamada expirado.", "error")
        return
    if sess["class_code"] != g.lfa_user["class_code"]:
        flash("Código pertence a outra turma.", "error")
        return
    try:
        db = get_lfa_db()
        db.execute("INSERT INTO attendance_records (session_id, user_id, created_at) VALUES (?, ?, ?)", (sess["id"], g.lfa_user["id"], now_iso()))
        db.execute("UPDATE users SET xp = xp + 10 WHERE id = ?", (g.lfa_user["id"],))
        db.commit()
        flash("Presença registrada.", "success")
    except sqlite3.IntegrityError:
        flash("Presença já registrada para esta chamada.", "warning")


def parse_grade(value: str | None):
    if value is None or value.strip() == "":
        return None
    try:
        grade = float(value.replace(",", "."))
    except ValueError:
        return None
    return max(0.0, min(10.0, grade))


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  role TEXT NOT NULL CHECK(role IN ('student', 'professor')),
  name TEXT NOT NULL,
  email TEXT UNIQUE,
  ra TEXT UNIQUE,
  class_code TEXT,
  password_hash TEXT,
  first_access INTEGER NOT NULL DEFAULT 1,
  xp INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS grades (
  user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  np1 REAL,
  np2 REAL,
  nt REAL,
  exam REAL
);
CREATE TABLE IF NOT EXISTS materials (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance_sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token TEXT NOT NULL UNIQUE,
  topic TEXT NOT NULL,
  class_code TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  created_by INTEGER NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attendance_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id INTEGER NOT NULL REFERENCES attendance_sessions(id) ON DELETE CASCADE,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL,
  UNIQUE(session_id, user_id)
);
"""


def init_lfa_db() -> None:
    get_lfa_db()


@lfa_bp.route("/chamada/<token>/qrcode.svg")
def chamada_qrcode_svg(token: str):
    sess = query_one("SELECT * FROM attendance_sessions WHERE token = ?", (token.upper(),))
    if not sess:
        abort(404)
    target_url = f"{request.scheme}://{request.host}{url_for('lfa.student', token=sess['token'])}"
    img = qrcode.make(target_url, image_factory=qrcode.image.svg.SvgImage)
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return current_app.response_class(buf.getvalue(), mimetype="image/svg+xml")


@lfa_bp.route("/professor/chamada/<int:session_id>")
@lfa_role_required("professor")
def view_attendance_session(session_id: int):
    sess = query_one("SELECT * FROM attendance_sessions WHERE id = ?", (session_id,))
    if not sess:
        abort(404)
    students = query_all("""
        SELECT u.id, u.name, u.ra, u.class_code, r.created_at as checked_in_at
        FROM users u
        LEFT JOIN attendance_records r ON r.user_id = u.id AND r.session_id = ?
        WHERE u.role = 'student' AND u.class_code = ?
        ORDER BY u.name
    """, (session_id, sess["class_code"]))
    
    qrcode_url = url_for("lfa.chamada_qrcode_svg", token=sess["token"])
    target_url = f"{request.scheme}://{request.host}{url_for('lfa.student', token=sess['token'])}"
    
    return render_template("lfa_chamada_detail.html", sess=sess, students=students, qrcode_url=qrcode_url, target_url=target_url, current_user=g.lfa_user)


@lfa_bp.route("/professor/chamada/<int:session_id>/toggle-presenca", methods=["POST"])
@lfa_role_required("professor")
def toggle_student_attendance(session_id: int):
    validate_csrf()
    user_id = int(request.form.get("user_id", "0"))
    sess = query_one("SELECT * FROM attendance_sessions WHERE id = ?", (session_id,))
    if not sess:
        abort(404)
    
    record = query_one("SELECT * FROM attendance_records WHERE session_id = ? AND user_id = ?", (session_id, user_id))
    if record:
        execute("DELETE FROM attendance_records WHERE session_id = ? AND user_id = ?", (session_id, user_id))
        execute("UPDATE users SET xp = MAX(0, xp - 10) WHERE id = ?", (user_id,))
        flash("Presença removida.", "info")
    else:
        execute("INSERT INTO attendance_records (session_id, user_id, created_at) VALUES (?, ?, ?)", (session_id, user_id, now_iso()))
        execute("UPDATE users SET xp = xp + 10 WHERE id = ?", (user_id,))
        flash("Presença registrada manualmente.", "success")
        
    return redirect(url_for("lfa.view_attendance_session", session_id=session_id))
