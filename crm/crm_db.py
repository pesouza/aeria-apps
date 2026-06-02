"""
CRM Database — SQLite models for Aeria Apps CRM
Contacts, page views, comments, interactions, analytics.
"""

import json
import sqlite3
import re
from datetime import datetime, date
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).resolve().parent / "data" / "crm.db"

# Spam detection patterns (Brazilian Portuguese focused)
SPAM_PATTERNS = [
    r"compre\s+agora",
    r"ganhe\s+dinheiro",
    r"clique\s+aqui",
    r"promoção\s+imperdível",
    r"casa\s+de\s+apostas?",
    r"crypto\b",
    r"bitcoin",
    r"investimento",
    r"renda\s+extra",
    r"emagre[cs]",
    r"viagra",
    r"cigana",
    r"tigrinho",
    r"Fortune\s+(Tiger|Rabbit|Ox|Mouse)",
    r"jogo\s+do\s+tigrinho",
    r"aç[oó]es\s+da\s+apple",
    r"milagroso",
    r"curso\s+do\s+(tal|fulano)",
    r"receita\s+fácil",
    r"dinheiro\s+fácil",
    r"turbine\s+",
    r"consultor\s+financeiro",
    r"voucher",
    r"cupom\s+exclusivo",
    r"compra\s+coletiva",
    r"fábrica\s+de\s+dinheiro",
    r"sistema\s+de\s+apostas",
    r"robozinho",
    r"abrir\s+conta",
    r"depósito\s+mínimo",
    r"bônus\s+de",
]


def get_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS contacts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            email       TEXT    NOT NULL,
            phone       TEXT    DEFAULT '',
            company     TEXT    DEFAULT '',
            message     TEXT    DEFAULT '',
            source      TEXT    DEFAULT 'site',
            status      TEXT    DEFAULT 'new',
            notes       TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS page_views (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            path        TEXT    NOT NULL,
            ip          TEXT    DEFAULT '',
            referrer    TEXT    DEFAULT '',
            user_agent  TEXT    DEFAULT '',
            country     TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS comments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            email       TEXT    NOT NULL,
            content     TEXT    NOT NULL,
            page_path   TEXT    DEFAULT '/',
            is_spam     INTEGER DEFAULT 0,
            is_approved INTEGER DEFAULT 0,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS interactions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id  INTEGER NOT NULL,
            type        TEXT    NOT NULL DEFAULT 'note',
            content     TEXT    NOT NULL DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_views_date ON page_views(created_at);
        CREATE INDEX IF NOT EXISTS idx_views_path ON page_views(path);
        CREATE INDEX IF NOT EXISTS idx_comments_spam ON comments(is_spam);
        CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(status);
        CREATE INDEX IF NOT EXISTS idx_contacts_created ON contacts(created_at);
    """)
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════════════════════════════════
#  CONTACTS (CRM Leads / Users)
# ═══════════════════════════════════════════════════════════════════════════

def add_contact(name: str, email: str, phone: str = "", message: str = "",
                source: str = "site") -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO contacts (name, email, phone, message, source) VALUES (?,?,?,?,?)",
        (name, email, phone, message, source),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid


def get_contacts(status: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[dict]:
    conn = get_db()
    if status:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM contacts ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_contacts(query: str) -> list[dict]:
    conn = get_db()
    like = f"%{query}%"
    rows = conn.execute(
        """SELECT * FROM contacts
           WHERE name LIKE ? OR email LIKE ? OR phone LIKE ? OR company LIKE ?
           ORDER BY created_at DESC LIMIT 50""",
        (like, like, like, like),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_contact(cid: int) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM contacts WHERE id=?", (cid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_contact(cid: int, **kwargs):
    allowed = {"name", "email", "phone", "company", "message", "source", "status", "notes"}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return
    fields["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [cid]
    conn = get_db()
    conn.execute(f"UPDATE contacts SET {set_clause} WHERE id=?", vals)
    conn.commit()
    conn.close()


def delete_contact(cid: int):
    conn = get_db()
    conn.execute("DELETE FROM contacts WHERE id=?", (cid,))
    conn.commit()
    conn.close()


def get_contacts_count(status: Optional[str] = None) -> int:
    conn = get_db()
    if status:
        row = conn.execute("SELECT COUNT(*) as c FROM contacts WHERE status=?", (status,)).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) as c FROM contacts").fetchone()
    conn.close()
    return row["c"]


def get_contacts_by_source() -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT source, COUNT(*) as total FROM contacts GROUP BY source ORDER BY total DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE VIEWS (Analytics)
# ═══════════════════════════════════════════════════════════════════════════

def track_view(path: str, ip: str = "", referrer: str = "", user_agent: str = "", country: str = ""):
    conn = get_db()
    conn.execute(
        "INSERT INTO page_views (path, ip, referrer, user_agent, country) VALUES (?,?,?,?,?)",
        (path, ip, referrer, user_agent, country),
    )
    conn.commit()
    conn.close()


def get_views_today() -> int:
    today = date.today().isoformat()
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM page_views WHERE date(created_at)=?", (today,),
    ).fetchone()
    conn.close()
    return row["c"]


def get_unique_visitors_today() -> int:
    today = date.today().isoformat()
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(DISTINCT ip) as c FROM page_views WHERE date(created_at)=? AND ip != ''",
        (today,),
    ).fetchone()
    conn.close()
    return row["c"]


def get_views_all_time() -> int:
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) as c FROM page_views").fetchone()
    conn.close()
    return row["c"]


def get_views_by_day(days: int = 30) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        """SELECT date(created_at) as day, COUNT(*) as views
           FROM page_views
           WHERE created_at >= datetime('now', ?)
           GROUP BY day ORDER BY day""",
        (f"-{days} days",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_views_by_path(days: int = 7) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        """SELECT path, COUNT(*) as views
           FROM page_views
           WHERE created_at >= datetime('now', ?)
           GROUP BY path ORDER BY views DESC LIMIT 20""",
        (f"-{days} days",),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
#  COMMENTS & SPAM
# ═══════════════════════════════════════════════════════════════════════════

def add_comment(name: str, email: str, content: str, page_path: str = "/") -> tuple[int, bool]:
    is_spam = 1 if _is_spam(content, name, email) else 0
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO comments (name, email, content, page_path, is_spam) VALUES (?,?,?,?,?)",
        (name, email, content, page_path, is_spam),
    )
    conn.commit()
    cid = cur.lastrowid
    conn.close()
    return cid, bool(is_spam)


def _is_spam(content: str, name: str = "", email: str = "") -> bool:
    """Heuristic spam detection using regex patterns and basic checks."""
    text = f"{name} {email} {content}".lower()

    # Pattern-based detection
    for pat in SPAM_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return True

    # Too many links
    link_count = len(re.findall(r"https?://", text))
    if link_count >= 3:
        return True

    # Excessive SHOUTING
    if len(content) > 30:
        upper_ratio = sum(1 for c in content if c.isupper() and c.isalpha()) / max(1, sum(1 for c in content if c.isalpha()))
        if upper_ratio > 0.65:
            return True

    # Repeated characters (spam signal)
    if re.search(r"(.)\1{5,}", content):
        return True

    # Mostly symbols/numbers
    alpha_ratio = sum(1 for c in content if c.isalpha()) / max(1, len(content))
    if alpha_ratio < 0.3 and len(content) > 15:
        return True

    return False


def get_comments(spam_only: bool = False, approved_only: bool = False,
                 pending_only: bool = False, limit: int = 100, offset: int = 0) -> list[dict]:
    conn = get_db()
    where = []
    if spam_only:
        where.append("is_spam=1")
    if approved_only:
        where.append("is_approved=1 AND is_spam=0")
    if pending_only:
        where.append("is_spam=0 AND is_approved=0")
    where_str = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(
        f"SELECT * FROM comments {where_str} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_comments_count(spam_only: bool = False, pending_only: bool = False) -> int:
    conn = get_db()
    if spam_only:
        row = conn.execute("SELECT COUNT(*) as c FROM comments WHERE is_spam=1").fetchone()
    elif pending_only:
        row = conn.execute("SELECT COUNT(*) as c FROM comments WHERE is_spam=0 AND is_approved=0").fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) as c FROM comments").fetchone()
    conn.close()
    return row["c"]


def approve_comment(cid: int):
    conn = get_db()
    conn.execute("UPDATE comments SET is_approved=1, is_spam=0 WHERE id=?", (cid,))
    conn.commit()
    conn.close()


def mark_spam(cid: int):
    conn = get_db()
    conn.execute("UPDATE comments SET is_spam=1, is_approved=0 WHERE id=?", (cid,))
    conn.commit()
    conn.close()


def delete_comment(cid: int):
    conn = get_db()
    conn.execute("DELETE FROM comments WHERE id=?", (cid,))
    conn.commit()
    conn.close()


def auto_clean_spam() -> int:
    """Remove spam comments older than 30 days."""
    conn = get_db()
    deleted = conn.execute(
        "DELETE FROM comments WHERE is_spam=1 AND created_at < datetime('now', '-30 days')"
    ).rowcount
    conn.commit()
    conn.close()
    return deleted


def analyze_pending_comments() -> list[dict]:
    """Re-check pending comments for spam (e.g. for cron job)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM comments WHERE is_spam=0 AND is_approved=0"
    ).fetchall()
    results = []
    for row in rows:
        r = dict(row)
        if _is_spam(r["content"], r["name"], r["email"]):
            conn.execute("UPDATE comments SET is_spam=1 WHERE id=?", (r["id"],))
            r["flagged_spam"] = True
        else:
            r["flagged_spam"] = False
        results.append(r)
    conn.commit()
    conn.close()
    return results


# ═══════════════════════════════════════════════════════════════════════════
#  INTERACTIONS (CRM follow-ups)
# ═══════════════════════════════════════════════════════════════════════════

def add_interaction(contact_id: int, itype: str, content: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO interactions (contact_id, type, content) VALUES (?,?,?)",
        (contact_id, itype, content),
    )
    conn.commit()
    conn.close()


def get_interactions(contact_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM interactions WHERE contact_id=? ORDER BY created_at DESC",
        (contact_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════
#  DAILY REPORT
# ═══════════════════════════════════════════════════════════════════════════

def get_daily_report() -> dict:
    today = date.today().isoformat()
    conn = get_db()

    views_today = conn.execute(
        "SELECT COUNT(*) as c FROM page_views WHERE date(created_at)=?", (today,),
    ).fetchone()["c"]

    unique_today = conn.execute(
        "SELECT COUNT(DISTINCT ip) as c FROM page_views WHERE date(created_at)=? AND ip != ''",
        (today,),
    ).fetchone()["c"]

    views_week = conn.execute(
        "SELECT COUNT(*) as c FROM page_views WHERE created_at >= datetime('now', '-7 days')",
    ).fetchone()["c"]

    new_leads = conn.execute(
        "SELECT COUNT(*) as c FROM contacts WHERE date(created_at)=?", (today,),
    ).fetchone()["c"]

    total_leads = conn.execute("SELECT COUNT(*) as c FROM contacts").fetchone()["c"]

    comments_today = conn.execute(
        "SELECT COUNT(*) as c FROM comments WHERE date(created_at)=?", (today,),
    ).fetchone()["c"]

    spam_detected = conn.execute(
        "SELECT COUNT(*) as c FROM comments WHERE is_spam=1 AND date(created_at)=?", (today,),
    ).fetchone()["c"]

    spam_removed_today = conn.execute(
        "SELECT COUNT(*) as c FROM comments WHERE is_spam=1 AND is_approved=0 AND date(created_at)=?", (today,),
    ).fetchone()["c"]

    pending_comments = conn.execute(
        "SELECT COUNT(*) as c FROM comments WHERE is_spam=0 AND is_approved=0",
    ).fetchone()["c"]

    top_pages = conn.execute(
        """SELECT path, COUNT(*) as views FROM page_views
           WHERE date(created_at)=?
           GROUP BY path ORDER BY views DESC LIMIT 5""",
        (today,),
    ).fetchall()
    top_pages = [dict(r) for r in top_pages]

    leads_status = conn.execute(
        "SELECT status, COUNT(*) as total FROM contacts GROUP BY status ORDER BY total DESC"
    ).fetchall()
    leads_status = [dict(r) for r in leads_status]

    conn.close()
    return {
        "date": today,
        "views_today": views_today,
        "unique_visitors": unique_today,
        "views_week": views_week,
        "new_leads": new_leads,
        "total_leads": total_leads,
        "comments_today": comments_today,
        "spam_detected": spam_detected,
        "spam_removed_today": spam_removed_today,
        "pending_comments": pending_comments,
        "top_pages": top_pages,
        "leads_status": leads_status,
    }
