"""
Aeria Apps CRM — Self-contained Flask CRM service
==================================================
Endpoints:
  /api/track       — JS beacon page view tracking
  /api/comment     — Submit a comment
  /api/lead        — CRM lead capture
  /admin/*         — Admin dashboard (contacts, comments, analytics)
  /api/crm/stats   — Stats for external cron job
"""

import json
import os
import logging
from datetime import date
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, render_template, request, session, redirect, url_for, flash, send_file

import crm_db
import auth_db

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv("CRM_SECRET_KEY", "crm-change-me-in-production-aeria-2026")
app.config["ADMIN_PASSWORD"] = os.getenv("CRM_ADMIN_PASSWORD", "admin123")
app.config["SITE_URL"] = os.getenv("SITE_URL", "https://aeria-apps.com.br")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("aeria-crm")


# ── Root redirect ────────────────────────────────────────────

@app.route("/")
def index():
    if session.get("client_logged_in"):
        return redirect(url_for("client_dashboard"))
    return render_template("client_landing.html")


# ── Initialise DB on first import ───────────────────────────────────────────
crm_db.init_db()


# ── Auth helpers ────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════════════════════
#  CLIENT AUTH (Selfware Client Area)
# ═══════════════════════════════════════════════════════════════════════════

def client_login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("client_logged_in"):
            return redirect(url_for("auth_login"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def auth_login():
    if session.get("client_logged_in"):
        return redirect(url_for("client_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        user = auth_db.authenticate(email, password)
        if user:
            session["client_logged_in"] = True
            session["client_user_id"] = user["id"]
            session["client_name"] = user["name"]
            flash(f"Bem-vindo, {user['name'].split()[0]}!", "success")
            return redirect(url_for("client_dashboard"))
        else:
            flash("E-mail ou senha incorretos", "error")

    return render_template("client_login.html")


@app.route("/register", methods=["GET", "POST"])
def auth_register():
    if session.get("client_logged_in"):
        return redirect(url_for("client_dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        company = request.form.get("company", "").strip()
        phone = request.form.get("phone", "").strip()

        if not name or not email or not password:
            flash("Nome, e-mail e senha são obrigatórios", "error")
            return render_template("client_register.html")

        if len(password) < 6:
            flash("Senha deve ter no mínimo 6 caracteres", "error")
            return render_template("client_register.html")

        try:
            user = auth_db.register_user(name, email, password, company, phone)
            session["client_logged_in"] = True
            session["client_user_id"] = user["id"]
            session["client_name"] = user["name"]
            flash("Conta criada com sucesso!", "success")
            return redirect(url_for("client_dashboard"))
        except ValueError as e:
            flash(str(e), "error")

    return render_template("client_register.html")


@app.route("/dashboard")
@client_login_required
def client_dashboard():
    user = auth_db.get_user(session["client_user_id"])
    if not user:
        session.clear()
        return redirect(url_for("auth_login"))
    return render_template("client_dashboard.html", user=user)


@app.route("/logout")
def auth_logout():
    session.pop("client_logged_in", None)
    session.pop("client_user_id", None)
    session.pop("client_name", None)
    flash("Você saiu da sua conta", "success")
    return redirect(url_for("auth_login"))


# ═══════════════════════════════════════════════════════════════════════════
#  SELFWARE ACADEMY
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/academy")
@client_login_required
def academy_index():
    user = auth_db.get_user(session["client_user_id"])
    courses = auth_db.list_courses(user["tier"] if user else "free")
    # add progress to each course
    for c in courses:
        c["completed"] = auth_db.count_completed_lessons(user["id"], c["key"])
        c["total"] = auth_db.count_total_lessons(c["key"])
    return render_template("client_academy.html", user=user, courses=courses)


@app.route("/academy/<course_key>")
@client_login_required
def academy_course(course_key):
    user = auth_db.get_user(session["client_user_id"])
    course = auth_db.get_course(course_key)
    if not course:
        flash("Curso não encontrado", "error")
        return redirect(url_for("academy_index"))

    # Check tier access
    tiers_allowed = {"free": ["free"], "premium": ["free", "premium"], "vip": ["free", "premium", "vip"]}
    if course["tier"] not in tiers_allowed.get(user["tier"], ["free"]):
        flash("Este curso requer um plano superior", "error")
        return redirect(url_for("academy_index"))

    lessons = auth_db.list_lessons(course_key)
    progress = auth_db.get_progress(user["id"])
    progress_map = {(p["course_key"], p["lesson_key"]): p["completed"] for p in progress}

    for l in lessons:
        l["completed"] = progress_map.get((course_key, l["key"]), 0)

    completed = auth_db.count_completed_lessons(user["id"], course_key)
    total = auth_db.count_total_lessons(course_key)

    return render_template(
        "client_course.html",
        user=user, course=course, lessons=lessons,
        completed=completed, total=total,
    )


@app.route("/academy/<course_key>/<lesson_key>")
@client_login_required
def academy_lesson(course_key, lesson_key):
    user = auth_db.get_user(session["client_user_id"])
    course = auth_db.get_course(course_key)
    lesson = auth_db.get_lesson(course_key, lesson_key)

    if not course or not lesson:
        flash("Aula não encontrada", "error")
        return redirect(url_for("academy_index"))

    # Mark as completed when viewed
    auth_db.save_progress(user["id"], course_key, lesson_key, completed=True)

    lessons = auth_db.list_lessons(course_key)
    progress = auth_db.get_progress(user["id"])
    progress_map = {(p["course_key"], p["lesson_key"]): p["completed"] for p in progress}
    for l in lessons:
        l["completed"] = progress_map.get((course_key, l["key"]), 0)

    completed = auth_db.count_completed_lessons(user["id"], course_key)
    total = auth_db.count_total_lessons(course_key)

    # Find next/prev lessons
    idx = next((i for i, l in enumerate(lessons) if l["key"] == lesson_key), -1)
    prev_lesson = lessons[idx - 1] if idx > 0 else None
    next_lesson = lessons[idx + 1] if idx < len(lessons) - 1 else None

    return render_template(
        "client_lesson.html",
        user=user, course=course, lesson=lesson,
        lessons=lessons, completed=completed, total=total,
        prev_lesson=prev_lesson, next_lesson=next_lesson,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  TEMPLATE LIBRARY
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/templates")
@client_login_required
def template_library():
    user = auth_db.get_user(session["client_user_id"])
    templates = auth_db.list_templates(user["tier"] if user else "free")
    categories = sorted(set(t["category"] for t in templates if t["category"]))
    return render_template(
        "client_templates.html",
        user=user, templates=templates, categories=categories,
    )


@app.route("/templates/<template_key>/download")
@client_login_required
def template_download(template_key):
    tpl = auth_db.get_template(template_key)
    if not tpl:
        flash("Template não encontrado", "error")
        return redirect(url_for("template_library"))
    file_path = Path(auth_db.BASE_DIR) / tpl["file_path"]
    if not file_path.exists():
        flash("Arquivo não encontrado", "error")
        return redirect(url_for("template_library"))
    return send_file(str(file_path), as_attachment=True, download_name=f"{tpl['key']}.{tpl['file_type']}")


# ═══════════════════════════════════════════════════════════════════════════
#  COMMUNITY — Forum
# ═══════════════════════════════════════════════════════════════════════════

CATEGORY_EMOJI = {
    "geral": "💬", "cases": "🏆", "cursos": "📚", "ideias": "💡",
}

@app.route("/community")
def community_index():
    if not session.get("client_logged_in"):
        return redirect(url_for("auth_login"))
    user = auth_db.get_user(session["client_user_id"])
    all_topics = auth_db.list_topics()
    topics = []
    for t in all_topics:
        cat = t["category"]
        t["icon"] = CATEGORY_EMOJI.get(cat, "💬")
        reply_count = auth_db.get_topic_reply_count(t["id"])
        t["reply_count"] = reply_count
        topics.append(t)
    categories = {"geral": "Geral", "cases": "Cases de Sucesso", "cursos": "Cursos", "ideias": "Ideias"}
    return render_template("client_community.html", user=user, topics=topics, categories=categories)


@app.route("/community/topic/<topic_key>", methods=["GET", "POST"])
def community_topic(topic_key):
    if not session.get("client_logged_in"):
        return redirect(url_for("auth_login"))
    user = auth_db.get_user(session["client_user_id"])
    topic = auth_db.get_topic(topic_key)
    if not topic:
        flash("Tópico não encontrado", "error")
        return redirect(url_for("community_index"))
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        if content:
            auth_db.add_reply(topic["id"], user["id"], content)
            return redirect(url_for("community_topic", topic_key=topic_key))
        flash("Digite uma resposta", "warning")
    replies = auth_db.get_topic_replies(topic["id"])
    return render_template("client_topic.html", user=user, topic=topic, replies=replies,
                           emoji=CATEGORY_EMOJI)


@app.route("/community/new", methods=["GET", "POST"])
def community_new_topic():
    if not session.get("client_logged_in"):
        return redirect(url_for("auth_login"))
    user = auth_db.get_user(session["client_user_id"])
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        desc = request.form.get("description", "").strip()
        category = request.form.get("category", "geral")
        if title and desc:
            import re
            key = re.sub(r"[^a-z0-9-]", "", title.lower().replace(" ", "-"))[:60]
            auth_db.create_topic(key, title, desc, category, user["id"])
            flash("Tópico criado!", "success")
            return redirect(url_for("community_topic", topic_key=key))
        flash("Preencha título e descrição", "warning")
    return render_template("client_new_topic.html", user=user, categories=CATEGORY_EMOJI)


# ═══════════════════════════════════════════════════════════════════════════
#  EVENTS
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/events")
def events_index():
    if not session.get("client_logged_in"):
        return redirect(url_for("auth_login"))
    user = auth_db.get_user(session["client_user_id"])
    events = auth_db.list_upcoming_events()
    for e in events:
        e["is_registered"] = auth_db.is_registered(e["id"], user["id"])
        e["type_icon"] = {"live": "🔴", "workshop": "🛠️", "roast": "🔥"}.get(e["event_type"], "📅")
    return render_template("client_events.html", user=user, events=events)


@app.route("/events/register/<event_key>", methods=["POST"])
def event_register(event_key):
    if not session.get("client_logged_in"):
        return redirect(url_for("auth_login"))
    user = auth_db.get_user(session["client_user_id"])
    event = auth_db.get_event(event_key)
    if event:
        auth_db.register_for_event(event["id"], user["id"])
        flash("Inscrição confirmada!", "success")
    return redirect(url_for("events_index"))


# ═══════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/api/track", methods=["GET", "POST"])
def track():
    """JS beacon / tracking pixel endpoint."""
    path = request.args.get("path", "/")
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        path = data.get("path", path)

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
    if ip:
        ip = ip.split(",")[0].strip()
    referrer = request.headers.get("Referer", "")
    ua = request.headers.get("User-Agent", "")

    crm_db.track_view(path, ip, referrer, ua)

    # Return 1x1 transparent GIF for GET (tracking pixel)
    if request.method == "GET":
        pixel = (
            b"GIF89a\x01\x00\x01\x00\x80\x01\x00\x00\x00\x00\xff\xff\xff"
            b"!\xf9\x04\x01\x0a\x00\x01\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
            b"\x00\x02\x02L\x01\x00;"
        )
        return (pixel, 200, {"Content-Type": "image/gif", "Cache-Control": "no-store"})

    return jsonify({"ok": True})


@app.route("/api/comment", methods=["POST"])
def submit_comment():
    """Submit a comment — auto-flagged as spam if detected."""
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    content = (data.get("content") or "").strip()
    page_path = (data.get("page_path") or "/").strip()

    if not name or not email or not content:
        return jsonify({"error": "name, email e content são obrigatórios"}), 400

    cid, is_spam = crm_db.add_comment(name, email, content, page_path)
    return jsonify({
        "ok": True,
        "id": cid,
        "is_spam": is_spam,
        "message": "Spam detectado e bloqueado" if is_spam else "Comentário recebido para aprovação",
    })


@app.route("/api/lead", methods=["POST"])
def capture_lead():
    """Capture a CRM lead (used by the site's contact form)."""
    data = request.get_json(silent=True) or request.form
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    phone = (data.get("whatsapp") or data.get("phone") or "").strip()
    message = (data.get("message") or "").strip()
    source = (data.get("source") or "site").strip()

    if not name or not email:
        return jsonify({"error": "Nome e e-mail são obrigatórios"}), 400

    cid = crm_db.add_contact(name, email, phone, message, source)
    logger.info("New lead #%d: %s <%s>", cid, name, email)

    # Log to legacy file too (backward compat)
    log_path = DATA_DIR / "leads.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[LEAD #{cid}] Nome: {name} | Email: {email} | WhatsApp: {phone} | Fonte: {source}\n")
    except OSError:
        pass

    return jsonify({"ok": True, "id": cid}), 200


@app.route("/api/crm/stats")
def api_stats():
    """Daily stats endpoint for cron job or external integration."""
    report = crm_db.get_daily_report()
    report["auto_cleaned"] = crm_db.auto_clean_spam()

    # Re-check pending comments for spam
    rechecked = crm_db.analyze_pending_comments()
    report["rechecked_comments"] = len(rechecked)
    report["newly_flagged"] = sum(1 for r in rechecked if r["flagged_spam"])

    return jsonify(report)


@app.route("/api/crm/contacts")
def api_contacts():
    """List contacts (with optional status filter)."""
    status = request.args.get("status")
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    query = request.args.get("q")

    if query:
        contacts = crm_db.search_contacts(query)
    else:
        contacts = crm_db.get_contacts(status, limit, offset)
    return jsonify(contacts)


# ═══════════════════════════════════════════════════════════════════════════
#  ADMIN PANEL
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == app.config["ADMIN_PASSWORD"]:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Senha incorreta", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_dashboard():
    report = crm_db.get_daily_report()
    views_by_day = crm_db.get_views_by_day(14)
    contacts_by_source = crm_db.get_contacts_by_source()
    return render_template(
        "admin_dashboard.html",
        report=report,
        views_by_day=json.dumps(views_by_day),
        contacts_by_source=contacts_by_source,
    )


@app.route("/admin/contacts")
@login_required
def admin_contacts():
    status = request.args.get("status")
    query = request.args.get("q")
    page = int(request.args.get("page", 1))
    limit = 20
    offset = (page - 1) * limit

    if query:
        contacts = crm_db.search_contacts(query)
        total = len(contacts)
    else:
        contacts = crm_db.get_contacts(status, limit, offset)
        total = crm_db.get_contacts_count(status)
    return render_template(
        "admin_contacts.html",
        contacts=contacts,
        total=total,
        page=page,
        limit=limit,
        status=status,
        query=query,
    )


@app.route("/admin/contacts/<int:cid>")
@login_required
def admin_contact_detail(cid):
    contact = crm_db.get_contact(cid)
    if not contact:
        return "Contato não encontrado", 404
    interactions = crm_db.get_interactions(cid)
    return render_template("admin_contact.html", contact=contact, interactions=interactions)


@app.route("/admin/contacts/<int:cid>/update", methods=["POST"])
@login_required
def admin_contact_update(cid):
    data = request.form
    crm_db.update_contact(
        cid,
        name=data.get("name"),
        email=data.get("email"),
        phone=data.get("phone"),
        company=data.get("company"),
        status=data.get("status"),
        notes=data.get("notes"),
    )
    if data.get("interaction"):
        crm_db.add_interaction(cid, "note", data["interaction"])
    flash("Contato atualizado", "success")
    return redirect(url_for("admin_contact_detail", cid=cid))


@app.route("/admin/contacts/<int:cid>/delete", methods=["POST"])
@login_required
def admin_contact_delete(cid):
    crm_db.delete_contact(cid)
    flash("Contato removido", "success")
    return redirect(url_for("admin_contacts"))


@app.route("/admin/comments")
@login_required
def admin_comments():
    filter_type = request.args.get("filter", "pending")
    page = int(request.args.get("page", 1))
    limit = 30
    offset = (page - 1) * limit

    if filter_type == "spam":
        comments = crm_db.get_comments(spam_only=True, limit=limit, offset=offset)
        total = crm_db.get_comments_count(spam_only=True)
    elif filter_type == "approved":
        comments = crm_db.get_comments(approved_only=True, limit=limit, offset=offset)
        total = crm_db.get_comments_count()
    else:
        comments = crm_db.get_comments(pending_only=True, limit=limit, offset=offset)
        total = crm_db.get_comments_count(pending_only=True)

    return render_template(
        "admin_comments.html",
        comments=comments,
        total=total,
        page=page,
        limit=limit,
        filter=filter_type,
    )


@app.route("/admin/comments/<int:cid>/approve", methods=["POST"])
@login_required
def admin_comment_approve(cid):
    crm_db.approve_comment(cid)
    flash("Comentário aprovado", "success")
    return redirect(request.referrer or url_for("admin_comments"))


@app.route("/admin/comments/<int:cid>/spam", methods=["POST"])
@login_required
def admin_comment_spam(cid):
    crm_db.mark_spam(cid)
    flash("Marcado como spam", "success")
    return redirect(request.referrer or url_for("admin_comments"))


@app.route("/admin/comments/<int:cid>/delete", methods=["POST"])
@login_required
def admin_comment_delete(cid):
    crm_db.delete_comment(cid)
    flash("Comentário removido", "success")
    return redirect(request.referrer or url_for("admin_comments"))


@app.route("/admin/analytics")
@login_required
def admin_analytics():
    days = int(request.args.get("days", 14))
    views_by_day = crm_db.get_views_by_day(days)
    views_by_path = crm_db.get_views_by_path(days)
    total_views = crm_db.get_views_all_time()
    today_views = crm_db.get_views_today()
    unique_today = crm_db.get_unique_visitors_today()
    return render_template(
        "admin_analytics.html",
        views_by_day=json.dumps(views_by_day),
        views_by_path=views_by_path,
        total_views=total_views,
        today_views=today_views,
        unique_today=unique_today,
        days=days,
    )


# ── Health ──────────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    return {"status": "ok", "service": "aeria-crm"}


# ── Run ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
