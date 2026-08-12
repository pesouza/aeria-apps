# AtendeAI Demo

Landing page + simulador de agente comercial para negócios locais.

## Executar localmente

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8787
```

Acesse `http://localhost:8787`.

## API

- `GET /health`
- `GET /api/profiles`
- `POST /api/chat`
- `POST /api/leads`

O MVP usa respostas determinísticas por segmento para manter a demonstração estável e sem depender de uma chave de IA. O sistema aceita `OPENROUTER_API_KEY` opcional para usar LLM real; sem chave, usa fallback determinístico. A personalização fica disponível em `POST /api/customize`. O painel de leads usa `GET /api/leads` com o header `X-Admin-Token` configurado por `ATENDEAI_ADMIN_TOKEN`. Nunca coloque chaves no GitHub.
