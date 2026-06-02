import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

import secrets

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for

BASE_DIR = Path(__file__).resolve().parent
#CONTENT_FILE = BASE_DIR / "content.json"
CONTENT_FILE = Path(os.getenv("CONTENT_FILE", "data/content.json"))

app = Flask(__name__)
app.config["SITE_URL"] = os.getenv("SITE_URL", "https://aeria-apps.com.br")
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if "text/html" in response.content_type:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://pagead2.googlesyndication.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-src https://pagead2.googlesyndication.com; "
        )
    return response

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
app.config["ADSENSE_CLIENT_ID"] = os.getenv("ADSENSE_CLIENT_ID", "")

# ─── Email config (via env vars) ───
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "admin@aeria-cs.com.br")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@aeria-cs.com.br")

logger = logging.getLogger(__name__)

def default_content():
    return {
        "site_name": "Aeria Apps",
        "meta_title": "Aeria Apps | Selfwares — Sistemas Autônomos para Operações Reais",
        "meta_description": "Aeria Apps constrói selfwares para PMEs operacionais: sistemas que assumem tarefas repetitivas, acompanham processos, executam follow-ups e reduzem trabalho manual.",
        "canonical_url": os.getenv("SITE_URL", "https://aeria-apps.com.br"),
        "og_image": "",
        "hero_kicker": "Sistemas para reduzir fricção operacional",
        "hero_title": "Menos tarefas manuais. Mais operação fluindo.",
        "hero_text": "Aeria Apps constrói selfwares: sistemas que assumem tarefas repetitivas, acompanham processos, executam follow-ups e mantêm fluxos operacionais em movimento com menos dependência humana.",
        "primary_cta_label": "Falar no WhatsApp",
        "primary_cta_url": "https://wa.me/551231973198",
        "secondary_cta_label": "Ver portfólio",
        "secondary_cta_url": "#portfolio",
        "whatsapp_number": "+55 12 3197-3198",
        "whatsapp_url": "https://wa.me/551231973198",
        "email": "admin@aeria-cs.com.br",
        "stats": [
            {"value": "87", "label": "Menos atrasos — tarefas acompanhadas e executadas no tempo certo"},
            {"value": "64", "label": "Menos retrabalho — informações organizadas e processos com continuidade"},
            {"value": "100", "label": "Menos caos — fluxos centralizados, rastreáveis e operando continuamente"},
        ],
        "projects": [
            {
                "title": "Institucional premium",
                "category": "Website",
                "description": "Site moderno com seções estratégicas e CTA forte.",
                "tags": ["Branding", "Responsivo", "Conversão"],
            }
        ],
        "process": [
            {"step": "01", "title": "Definição", "text": "Você informa objetivo, identidade visual e projetos."},
            {"step": "02", "title": "Montagem", "text": "Estrutura, SEO e componentes são organizados."},
            {"step": "03", "title": "Publicação", "text": "A página entra no ar."},
        ],
        "faq": [
            {
                "q": "Posso alterar portfólio e textos sozinho?",
                "a": "Sim. O painel permite editar conteúdo sem mexer em código.",
            }
        ],
        "contact_title": "Vamos encontrar tarefas manuais que podem sair da sua rotina.",
        "contact_text": "Conte um pouco sobre sua operação. Em até 2 dias úteis eu mapeio gargalos, atrasos e tarefas repetitivas que um selfware pode assumir.",
        "footer_note": "Aeria Apps • Selfwares • Sistemas Autônomos • IA Operacional",
    }


def load_content():
    if not CONTENT_FILE.exists():
        return default_content()

    try:
        with CONTENT_FILE.open("r", encoding="utf-8") as f:
            content = json.load(f)

        fallback = default_content()
        fallback.update(content)
        return fallback

    except Exception as exc:
        content = default_content()
        content["hero_text"] = f"Erro ao ler content.json: {exc}"
        return content

@app.get("/")
def index():
    return render_template("index.html", content=load_content())


@app.get("/robots.txt")
def robots():
    site_url = app.config["SITE_URL"]
    body = f"""User-agent: *
Disallow:
Sitemap: {site_url}/sitemap.xml
"""
    return Response(body, mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap():
    site_url = app.config["SITE_URL"]
    sections = [
        "", "selfware", "applications", "real-scenarios",
        "before-after", "infrastructure", "contact",
    ]
    urls = "\n".join(
        f'  <url>\n    <loc>{site_url}/#{s}</loc>\n    <priority>{"1.0" if not s else "0.8"}</priority>\n  </url>'
        for s in sections
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
"""
    return Response(xml, mimetype="application/xml")


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/contact")
def contact_api():
    try:
        data = request.get_json()

        if not data:
            return jsonify({"error": "JSON inválido"}), 400

        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()

        if not name or not email:
            return jsonify({"error": "Nome e e-mail são obrigatórios"}), 400

        whatsapp = data.get("whatsapp", "")
        message = data.get("message", "")

        # Log the lead
        log_line = f"[LEAD] Nome: {name} | Email: {email} | WhatsApp: {whatsapp} | Mensagem: {message[:120]}"
        print(log_line)

        # Append to a leads log file
        log_path = BASE_DIR / "data" / "leads.log"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{log_line}\n")
        except OSError:
            pass

        # Send email notification (if SMTP is configured)
        send_notification_email(name, email, whatsapp, message)

        return jsonify({"status": "ok", "message": "Lead recebido com sucesso"}), 200

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def send_notification_email(name, email, whatsapp, message):
    """Envia e-mail de notificação sobre novo lead via SMTP (se configurado)."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        logger.info("SMTP não configurado — notificação por e-mail ignorada.")
        return

    body = f"""Novo lead recebido pelo site Aeria Apps:

Nome: {name}
E-mail: {email}
WhatsApp: {whatsapp or "(não informado)"}
Mensagem: {message or "(não informada)"}
"""

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"Novo lead: {name} — Aeria Apps"
    msg["From"] = EMAIL_FROM
    msg["To"] = NOTIFY_EMAIL

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        logger.info("E-mail de notificação enviado para %s", NOTIFY_EMAIL)
    except Exception as exc:
        logger.warning("Falha ao enviar e-mail de notificação: %s", exc)


# ─── Admin routes ───
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        return render_template("admin_login.html", error="Senha incorreta")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    content = load_content()
    if request.method == "POST":
        updated = default_content()
        # Merge with existing saved content to preserve extra keys (launch_date, testimonials, etc.)
        saved = {}
        if CONTENT_FILE.exists():
            try:
                saved = json.loads(CONTENT_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        updated.update(saved)
        # Override with form values for known keys
        for key in list(updated.keys()):
            if key == "testimonials":
                continue
            if key in request.form:
                val = request.form[key].strip()
                if val:
                    updated[key] = val
        # Handle extra fields not in default_content
        for key in ("launch_date",):
            if key in request.form and request.form[key].strip():
                updated[key] = request.form[key].strip()
        # Handle testimonials JSON
        if request.form.get("testimonials_json", "").strip():
            try:
                updated["testimonials"] = json.loads(request.form["testimonials_json"])
            except json.JSONDecodeError:
                pass
        CONTENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with CONTENT_FILE.open("w", encoding="utf-8") as f:
            json.dump(updated, f, ensure_ascii=False, indent=2)
        return redirect(url_for("admin"))
    return render_template("admin.html", content=content)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
