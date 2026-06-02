"""
Auth Database — Client login and user management for Aeria Apps.
SQLite-based, stores user accounts with hashed passwords.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "auth.db"


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            email       TEXT    NOT NULL UNIQUE,
            password    TEXT    NOT NULL,
            company     TEXT    DEFAULT '',
            phone       TEXT    DEFAULT '',
            tier        TEXT    DEFAULT 'free',
            is_admin    INTEGER DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS user_progress (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            course_key  TEXT    NOT NULL,
            lesson_key  TEXT    NOT NULL,
            completed   INTEGER DEFAULT 0,
            completed_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS courses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key         TEXT    NOT NULL UNIQUE,
            title       TEXT    NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            tier        TEXT    NOT NULL DEFAULT 'free',
            image_url   TEXT    DEFAULT '',
            icon        TEXT    DEFAULT '📚',
            sort_order  INTEGER DEFAULT 0,
            unlock_days INTEGER DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS lessons (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            course_key  TEXT    NOT NULL,
            key         TEXT    NOT NULL,
            title       TEXT    NOT NULL,
            content     TEXT    NOT NULL DEFAULT '',
            video_url   TEXT    DEFAULT '',
            duration    TEXT    DEFAULT '',
            sort_order  INTEGER DEFAULT 0,
            lesson_type TEXT    DEFAULT 'text',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (course_key) REFERENCES courses(key) ON DELETE CASCADE,
            UNIQUE(course_key, key)
        );

        CREATE TABLE IF NOT EXISTS templates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key         TEXT    NOT NULL UNIQUE,
            title       TEXT    NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            category    TEXT    DEFAULT '',
            tier        TEXT    NOT NULL DEFAULT 'free',
            file_path   TEXT    NOT NULL,
            file_type   TEXT    DEFAULT 'md',
            icon        TEXT    DEFAULT '📄',
            sort_order  INTEGER DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_progress_user ON user_progress(user_id);
        CREATE INDEX IF NOT EXISTS idx_lessons_course ON lessons(course_key);
        CREATE INDEX IF NOT EXISTS idx_templates_category ON templates(category);

        CREATE TABLE IF NOT EXISTS forum_topics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key         TEXT    NOT NULL UNIQUE,
            title       TEXT    NOT NULL,
            description TEXT    DEFAULT '',
            category    TEXT    DEFAULT 'geral',
            course_key  TEXT    DEFAULT NULL,
            created_by  INTEGER,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS forum_replies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id    INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            content     TEXT    NOT NULL,
            upvotes     INTEGER DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (topic_id) REFERENCES forum_topics(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key         TEXT    NOT NULL UNIQUE,
            title       TEXT    NOT NULL,
            description TEXT    DEFAULT '',
            event_type  TEXT    DEFAULT 'live',
            event_date  TEXT    NOT NULL,
            event_time  TEXT    DEFAULT '19:00',
            url         TEXT    DEFAULT '',
            created_by  INTEGER DEFAULT NULL,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS event_registrations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id    INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            registered_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(event_id, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_forum_category ON forum_topics(category);
        CREATE INDEX IF NOT EXISTS idx_replies_topic ON forum_replies(topic_id);
        CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);
    """)
    conn.commit()
    conn.close()

    _seed_courses()
    _seed_templates()
    _seed_community()


def register_user(name, email, password, company="", phone=""):
    """Register a new user. Returns user dict or raises ValueError."""
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM users WHERE email=?", (email,)
    ).fetchone()
    if existing:
        conn.close()
        raise ValueError("E-mail já cadastrado")
    pwhash = generate_password_hash(password)
    cur = conn.execute(
        "INSERT INTO users (name, email, password, company, phone) VALUES (?,?,?,?,?)",
        (name, email, pwhash, company, phone),
    )
    conn.commit()
    uid = cur.lastrowid
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return dict(row)


def authenticate(email, password):
    """Verify credentials. Returns user dict or None."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE email=?", (email,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    user = dict(row)
    if check_password_hash(user["password"], password):
        return user
    return None


def get_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_email(email):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_user(user_id, **kwargs):
    allowed = {"name", "company", "phone", "tier"}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return
    fields["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [user_id]
    conn = get_db()
    conn.execute(f"UPDATE users SET {set_clause} WHERE id=?", vals)
    conn.commit()
    conn.close()


def get_progress(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM user_progress WHERE user_id=? ORDER BY course_key, lesson_key",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_progress(user_id, course_key, lesson_key, completed=True):
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM user_progress WHERE user_id=? AND course_key=? AND lesson_key=?",
        (user_id, course_key, lesson_key),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE user_progress SET completed=?, completed_at=? WHERE id=?",
            (1 if completed else 0,
             datetime.utcnow().isoformat() if completed else None,
             existing["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO user_progress (user_id, course_key, lesson_key, completed, completed_at) VALUES (?,?,?,?,?)",
            (user_id, course_key, lesson_key,
             1 if completed else 0,
             datetime.utcnow().isoformat() if completed else None),
        )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
#  COURSES
# ──────────────────────────────────────────────

def list_courses(user_tier="free"):
    """List courses accessible to the user's tier."""
    conn = get_db()
    tiers = ["free"]
    if user_tier in ("premium", "vip"):
        tiers.append("premium")
    if user_tier == "vip":
        tiers.append("vip")
    placeholders = ",".join("?" for _ in tiers)
    rows = conn.execute(
        f"SELECT * FROM courses WHERE tier IN ({placeholders}) ORDER BY sort_order",
        tiers,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_course(course_key):
    conn = get_db()
    row = conn.execute("SELECT * FROM courses WHERE key=?", (course_key,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_course(key, title, description="", tier="free", icon="📚", sort_order=0):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO courses (key, title, description, tier, icon, sort_order) VALUES (?,?,?,?,?,?)",
        (key, title, description, tier, icon, sort_order),
    )
    conn.commit()
    conn.close()


def delete_course(course_key):
    conn = get_db()
    conn.execute("DELETE FROM lessons WHERE course_key=?", (course_key,))
    conn.execute("DELETE FROM courses WHERE key=?", (course_key,))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
#  LESSONS
# ──────────────────────────────────────────────

def list_lessons(course_key):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM lessons WHERE course_key=? ORDER BY sort_order",
        (course_key,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_lesson(course_key, lesson_key):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM lessons WHERE course_key=? AND key=?",
        (course_key, lesson_key),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_lesson(course_key, key, title, content="", video_url="", duration="", sort_order=0, lesson_type="text"):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO lessons (course_key, key, title, content, video_url, duration, sort_order, lesson_type) VALUES (?,?,?,?,?,?,?,?)",
        (course_key, key, title, content, video_url, duration, sort_order, lesson_type),
    )
    conn.commit()
    conn.close()


def count_completed_lessons(user_id, course_key):
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM user_progress WHERE user_id=? AND course_key=? AND completed=1",
        (user_id, course_key),
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def count_total_lessons(course_key):
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM lessons WHERE course_key=?",
        (course_key,),
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


# ──────────────────────────────────────────────
#  TEMPLATES
# ──────────────────────────────────────────────

def list_templates(user_tier="free"):
    conn = get_db()
    tiers = ["free"]
    if user_tier in ("premium", "vip"):
        tiers.append("premium")
    if user_tier == "vip":
        tiers.append("vip")
    placeholders = ",".join("?" for _ in tiers)
    rows = conn.execute(
        f"SELECT * FROM templates WHERE tier IN ({placeholders}) ORDER BY sort_order",
        tiers,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_template(template_key):
    conn = get_db()
    row = conn.execute("SELECT * FROM templates WHERE key=?", (template_key,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_template(key, title, description="", category="", tier="free", file_path="", file_type="md", icon="📄", sort_order=0):
    conn = get_db()
    conn.execute(
        "INSERT OR IGNORE INTO templates (key, title, description, category, tier, file_path, file_type, icon, sort_order) VALUES (?,?,?,?,?,?,?,?,?)",
        (key, title, description, category, tier, file_path, file_type, icon, sort_order),
    )
    conn.commit()
    conn.close()


def _seed_community():
    conn = get_db()
    topics = [
        ("apresente-se", "Apresente-se! 👋",
         "Conte um pouco sobre você e sua empresa. Qual problema você quer resolver com agentes de IA?",
         "geral"),
        ("cases-sucesso", "Cases de Sucesso 🏆",
         "Compartilhe seus resultados usando agentes Selfware. Inspire a comunidade!",
         "cases"),
        ("duvidas-primeiro-agente", "Dúvidas sobre o curso 'Seu Primeiro Agente'",
         "Espaço para tirar dúvidas sobre as aulas do curso básico.",
         "cursos"),
        ("ideias-de-agentes", "Ideias de Agentes 💡",
         "Que tipo de agente você quer construir? Compartilhe ideias e peça feedback.",
         "ideias"),
    ]
    for key, title, desc, cat in topics:
        conn.execute(
            "INSERT OR IGNORE INTO forum_topics (key, title, description, category) VALUES (?,?,?,?)",
            (key, title, desc, cat),
        )

    # Seed events
    from datetime import datetime, timedelta
    today = datetime.now()
    events = [
        ("live-intro-agentes", "🔴 Live: Introdução aos Agentes Autônomos",
         "Vou mostrar na prática como construir um agente do zero em menos de 10 minutos.",
         "live", (today + timedelta(days=7)).strftime("%Y-%m-%d"), "19:00",
         "https://youtube.com/live/aeria-intro"),
        ("workshop-prompts", "🛠️ Workshop: Engenharia de Prompts",
         "Workshop prático de prompts avançados para agentes de IA.",
         "workshop", (today + timedelta(days=14)).strftime("%Y-%m-%d"), "15:00",
         "https://meet.google.com/aeria-workshop"),
        ("roast-agentes", "🔥 Selfware Roast #1",
         "Análise ao vivo de agentes construídos pela comunidade. Submeta o seu!",
         "roast", (today + timedelta(days=21)).strftime("%Y-%m-%d"), "20:00",
         "https://twitch.tv/aeria-roast"),
    ]
    for key, title, desc, etype, edate, etime, url in events:
        conn.execute(
            "INSERT OR IGNORE INTO events (key, title, description, event_type, event_date, event_time, url) VALUES (?,?,?,?,?,?,?)",
            (key, title, desc, etype, edate, etime, url),
        )
    conn.commit()
    conn.close()


def _seed_courses():
    conn = get_db()
    courses = [
        ("seu-primeiro-agente", "Seu Primeiro Agente de IA",
         "Aprenda a construir seu primeiro agente autônomo do zero. Sem código, sem mistério.",
         "free", "🤖", 1, 0),
        ("prompts-avancados", "Engenharia de Prompts para Agentes",
         "Domine a arte de criar prompts que fazem seu agente agir com precisão.",
         "premium", "🎯", 2, 0),
        ("agent-stack", "Stack Completo de Agentes",
         "Integre ferramentas, APIs e fluxos complexos.",
         "vip", "⚡", 3, 0),
    ]
    for c in courses:
        conn.execute(
            "INSERT OR IGNORE INTO courses (key, title, description, tier, icon, sort_order, unlock_days) VALUES (?,?,?,?,?,?,?)",
            c,
        )

    lessons = [
        ("seu-primeiro-agente", "o-que-e-um-agente", "O que é um agente de IA?",
         1, "5 min", "<p>Um <strong>agente de IA autônomo</strong> é um sistema que usa inteligência artificial para executar tarefas sem supervisão humana constante.</p>"),
        ("seu-primeiro-agente", "preparando-ambiente", "Preparando o Ambiente",
         2, "7 min", "<p>Você só precisa de um computador, um navegador e 5 minutos.</p>"),
        ("seu-primeiro-agente", "seu-primeiro-agente-pratico", "Mão na Massa",
         3, "10 min", "<p>Vamos criar seu primeiro agente que pesquisa preços automaticamente.</p>"),
        ("seu-primeiro-agente", "refinando-o-agente", "Refinando Seu Agente",
         4, "8 min", "<p>Dicas para melhorar seus resultados com instruções específicas.</p>"),
        ("seu-primeiro-agente", "proximos-passos", "Próximos Passos",
         5, "5 min", "<p>Você construiu seu primeiro agente! É só o começo.</p>"),
    ]
    for course_key, key, title, sort_order, duration, content in lessons:
        conn.execute(
            "INSERT OR IGNORE INTO lessons (course_key, key, title, content, duration, sort_order) VALUES (?,?,?,?,?,?)",
            (course_key, key, title, content, duration, sort_order),
        )
    conn.commit()
    conn.close()


def _seed_templates():
    conn = get_db()
    templates = [
        ("pesquisa-concorrentes", "Pesquisa de Concorrentes",
         "Prompt pronto para pesquisar concorrentes e gerar relatório comparativo",
         "Marketing", "free", "data/templates/pesquisa-concorrentes.md", "🔍", 1),
        ("atendimento-whatsapp", "Atendimento WhatsApp",
         "Estrutura para agente de atendimento via WhatsApp",
         "Vendas", "free", "data/templates/atendimento-whatsapp.md", "💬", 2),
        ("analise-financeira", "Análise Financeira Rápida",
         "Agente para analisar demonstrações financeiras e gerar insights",
         "Financeiro", "premium", "data/templates/analise-financeira.md", "📊", 3),
        ("gerador-relatorios", "Gerador de Relatórios",
         "Template para agente que coleta dados e gera relatórios periódicos",
         "Operações", "premium", "data/templates/gerador-relatorios.md", "📋", 4),
    ]
    for t in templates:
        conn.execute(
            "INSERT OR IGNORE INTO templates (key, title, description, category, tier, file_path, icon, sort_order) VALUES (?,?,?,?,?,?,?,?)",
            t,
        )
    conn.commit()

init_db()
