from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
CONTENT_FILE = Path(os.getenv('CONTENT_FILE', BASE_DIR / 'data' / 'content.json'))

INDICA_DB = Path(os.getenv('INDICA_DB', '/data/indica-aqui/indica_aqui.db'))

app = Flask(__name__, static_folder='static', template_folder='templates')


def get_indica_db():
    """Abre conexão com o banco do Indica Aqui."""
    conn = sqlite3.connect(str(INDICA_DB))
    conn.row_factory = sqlite3.Row
    return conn


def load_content():
    try:
        if CONTENT_FILE.exists():
            return json.loads(CONTENT_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}


@app.get('/')
def index():
    return render_template('index.html', content=load_content())


@app.get('/health')
def health():
    return jsonify(status='ok')


# ─── Indica Aqui ───────────────────────────────────────────────────────

@app.get('/indicacoes/')
def indica_index():
    conn = get_indica_db()
    try:
        cur = conn.execute("""
            SELECT s.*,
                   COUNT(p.id) as total_prestadores,
                   COALESCE(SUM(p.total_indicacoes), 0) as total_indicacoes
            FROM servicos s
            LEFT JOIN prestadores p ON p.servico_id = s.id
            WHERE s.ativo = 1
            GROUP BY s.id
            ORDER BY s.nome
        """)
        servicos = [dict(r) for r in cur.fetchall()]

        cur = conn.execute("""
            SELECT COUNT(*) as tp, COALESCE(SUM(total_indicacoes), 0) as ti
            FROM prestadores
        """)
        stats_row = cur.fetchone()
        stats = {'total_prestadores': stats_row['tp'], 'total_indicacoes': stats_row['ti']}
    finally:
        conn.close()
    return render_template('indicacoes_index.html', servicos=servicos, stats=stats)


@app.get('/indicacoes/<slug>')
def indica_servico(slug):
    conn = get_indica_db()
    try:
        cur = conn.execute("SELECT * FROM servicos WHERE slug = ? AND ativo = 1", (slug,))
        servico = cur.fetchone()
        if not servico:
            abort(404)
        servico = dict(servico)

        cur = conn.execute("""
            SELECT * FROM prestadores
            WHERE servico_id = ?
            ORDER BY score DESC, total_indicacoes DESC
        """, (servico['id'],))
        prestadores = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return render_template('indicacoes_servico.html', servico=servico, prestadores=prestadores)


@app.get('/indicacoes/prestador/<int:prestador_id>')
def indica_prestador(prestador_id):
    conn = get_indica_db()
    try:
        cur = conn.execute("""
            SELECT p.*, s.nome as servico_nome, s.slug as servico_slug, s.icone
            FROM prestadores p
            JOIN servicos s ON p.servico_id = s.id
            WHERE p.id = ?
        """, (prestador_id,))
        prestador = cur.fetchone()
        if not prestador:
            abort(404)
        prestador = dict(prestador)

        cur = conn.execute("""
            SELECT * FROM avaliacoes
            WHERE prestador_id = ?
            ORDER BY created_at DESC
        """, (prestador_id,))
        avaliacoes = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return render_template('indicacoes_prestador.html', prestador=prestador, avaliacoes=avaliacoes)


# ─── Admin ─────────────────────────────────────────────────────────────
@app.get('/admin')
def admin():
    return render_template('admin.html')


@app.errorhandler(404)
def not_found(_):
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(_):
    return render_template('500.html'), 500
