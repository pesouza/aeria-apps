#!/usr/bin/env python3
"""
Aeria CRM — Daily Report Script
================================
Gera relatório diário de acessos, leads e spam.
Tenta primeiro via API (se o CRM estiver online).
Faz fallback para leitura direta do SQLite.
"""

import json
import sys
import os
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

# Config
CRM_API = os.getenv("CRM_API_URL", "https://crm.aeria-apps.com.br/api/crm/stats")
LOCAL_DB = Path(os.getenv("CRM_DB_PATH", "/opt/data/aeria-crm/data/crm.db"))


def fetch_via_api():
    """Try to get stats from the CRM service API."""
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = Request(CRM_API, method="GET")
        with urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read().decode())
        return data, "api"
    except (URLError, OSError, json.JSONDecodeError) as e:
        print(f"[CRM] API unavailable ({e}), falling back to local DB...", file=sys.stderr)
        return None, None


def fetch_local():
    """Read stats directly from local SQLite database."""
    if not LOCAL_DB.exists():
        print(f"[CRM] Local DB not found at {LOCAL_DB}", file=sys.stderr)
        return None

    try:
        sys.path.insert(0, str(LOCAL_DB.parent.parent))
        # Import the CRM db module
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "crm_db", LOCAL_DB.parent.parent / "crm_db.py"
        )
        if spec and spec.loader:
            crm_db = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(crm_db)
            return crm_db.get_daily_report()
    except Exception as e:
        print(f"[CRM] Local DB query failed: {e}", file=sys.stderr)
        return None


def format_report(data):
    """Format daily report as a WhatsApp-friendly message."""
    today = date.today()
    lines = []
    lines.append(f"📊 *Relatório Diário — {today.strftime('%d/%m/%Y')}*")
    lines.append("")

    # Access stats
    views = data.get("views_today", 0)
    unique = data.get("unique_visitors", 0)
    week = data.get("views_week", 0)
    lines.append(f"🌐 *Acessos*")
    lines.append(f"   Hoje: {views} ({unique} únicos)")
    lines.append(f"   Últimos 7 dias: {week}")

    # Top pages
    top = data.get("top_pages", [])
    if top:
        lines.append(f"   📄 Mais acessadas:")
        for p in top[:3]:
            lines.append(f"     {p.get('path','?')}: {p.get('views',0)}")
    lines.append("")

    # Leads
    new_leads = data.get("new_leads", 0)
    total_leads = data.get("total_leads", 0)
    lines.append(f"👥 *Leads*")
    lines.append(f"   Hoje: +{new_leads}")
    lines.append(f"   Total: {total_leads}")

    # Lead status breakdown
    leads_status = data.get("leads_status", [])
    if leads_status:
        for s in leads_status:
            lines.append(f"     {s.get('status','?')}: {s.get('total',0)}")
    lines.append("")

    # Comments & spam
    comments = data.get("comments_today", 0)
    spam = data.get("spam_detected", 0)
    pending = data.get("pending_comments", 0)
    flagged = data.get("newly_flagged", 0)
    cleaned = data.get("auto_cleaned", 0)

    lines.append(f"💬 *Comentários*")
    lines.append(f"   Hoje: {comments}")
    if spam:
        lines.append(f"   🚫 Spam detectado: {spam}")
    if flagged:
        lines.append(f"   ⚠️  Novos spams identificados: {flagged}")
    if pending:
        lines.append(f"   ⏳ Aguardando moderação: {pending}")
    if cleaned:
        lines.append(f"   🧹 Spam antigo removido: {cleaned}")
    lines.append("")

    # Summary line
    lines.append(f"Resumo: {views} visitas · +{new_leads} leads · 🚫{spam} spam bloqueado")
    lines.append("")
    lines.append("🔗 Acesse o painel: https://crm.aeria-apps.com.br/admin")

    return "\n".join(lines)


def main():
    data, source = fetch_via_api()
    if not data:
        data = fetch_local()
        source = "local"

    if not data:
        print("❌ Não foi possível obter dados do CRM. Verifique se o serviço está rodando.", file=sys.stderr)
        sys.exit(1)

    report = format_report(data)
    # Just print the report — Hermes cron will auto-deliver to WhatsApp
    print(report)


if __name__ == "__main__":
    main()
