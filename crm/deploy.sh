#!/bin/bash
# ============================================================
# Aeria CRM — Deploy Script
# Copia os arquivos para o workspace e inicia o container
# Execute como root ou com sudo
# ============================================================
set -euo pipefail

CRM_SRC="/opt/data/aeria-crm"
WORKSPACE="/workspace/aeria-apps"

echo "==> Copiando arquivos do CRM para $WORKSPACE/crm/..."
rm -rf "$WORKSPACE/crm"
cp -r "$CRM_SRC" "$WORKSPACE/crm"

echo "==> Ajustando permissões..."
chown -R root:root "$WORKSPACE/crm"

echo "==> Copiando tracker.js para o static do site..."
cp "$CRM_SRC/static/tracker.js" "$WORKSPACE/static/tracker.js"
chown root:root "$WORKSPACE/static/tracker.js"

echo "==> Pronto!"
echo ""
echo "Para iniciar o CRM via Docker:"
echo "  cd $WORKSPACE/crm"
echo "  docker compose up -d"
echo ""
echo "Depois configure o Traefik para rotear crm.aeria-apps.com.br para o container."
echo ""
echo "Para adicionar tracking ao site, edite templates/index.html e adicione:"
echo '  <script defer src="https://crm.aeria-apps.com.br/static/tracker.js"'
echo '          data-api="https://crm.aeria-apps.com.br/api/track"></script>'
echo ""
echo "Para substituir o endpoint /api/contact do site pelo CRM:"
echo "  - Edite $WORKSPACE/app.py para POST para http://crm:5001/api/lead"
echo "  - Ou mude o action do form JS para https://crm.aeria-apps.com.br/api/lead"
echo ""
echo "Painel Admin: https://crm.aeria-apps.com.br/admin"
echo "Senha padrão: admin123 (mude via env CRM_ADMIN_PASSWORD)"
