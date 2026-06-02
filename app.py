import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
#CONTENT_FILE = BASE_DIR / "content.json"
CONTENT_FILE = Path(os.getenv("CONTENT_FILE", "data/content.json"))

app = Flask(__name__)
app.config["SITE_URL"] = os.getenv("SITE_URL", "https://srv665265.hstgr.cloud")

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
        "meta_title": "Aeria Apps | Portfólio e soluções digitais",
        "meta_description": "Aeria Apps cria landing pages, sites institucionais e páginas de conversão.",
        "canonical_url": os.getenv("SITE_URL", "https://aeria-apps.com.br"),
        "og_image": "",
        "hero_kicker": "Portfólio digital com foco em conversão",
        "hero_title": "Seu trabalho apresentado com impacto.",
        "hero_text": "Página dinâmica, profissional e pronta para mostrar seus projetos.",
        "primary_cta_label": "Falar no WhatsApp",
        "primary_cta_url": "https://wa.me/551231973198",
        "secondary_cta_label": "Ver portfólio",
        "secondary_cta_url": "#portfolio",
        "whatsapp_number": "+55 12 3197-3198",
        "whatsapp_url": "https://wa.me/551231973198",
        "email": "admin@aeria-cs.com.br",
        "stats": [
            {"value": "SEO", "label": "estrutura otimizada para Google"},
            {"value": "DINÂMICO", "label": "conteúdo editável pelo painel"},
            {"value": "RÁPIDO", "label": "carregamento leve e responsivo"},
        ],
        "services": [
            {"title": "Landing pages", "text": "Páginas para captação de leads, campanhas e ofertas."},
            {"title": "Sites institucionais", "text": "Apresente sua empresa com clareza e credibilidade."},
            {"title": "SEO on-page", "text": "Estrutura pensada para indexação."},
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
        "contact_title": "Pronto para publicar seus trabalhos?",
        "contact_text": "Me chame no WhatsApp ou e-mail e eu atualizo a página com o seu conteúdo.",
        "footer_note": "Aeria Apps • portfólio e presença digital",
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
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{site_url}/</loc>
  </url>
</urlset>
"""
    return Response(xml, mimetype="application/xml")


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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
