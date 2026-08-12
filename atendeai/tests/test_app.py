import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))
os.environ.pop("OPENROUTER_API_KEY", None)
from app import app

client = TestClient(app)


def test_custom_profile_is_created_and_used():
    response = client.post("/api/customize", json={
        "business_name": "Studio Paulo",
        "segment": "Consultoria",
        "city": "São Paulo",
        "services": ["diagnóstico", "automação"],
        "goal": "agendar uma conversa",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["profile"]["name"] == "Studio Paulo"
    assert data["profile"]["services"] == ["diagnóstico", "automação"]
    assert data["profile_id"]


def test_chat_keeps_deterministic_fallback():
    response = client.post("/api/chat", json={
        "profile": "clinic",
        "message": "Quero agendar uma avaliação",
        "history": [],
    })
    assert response.status_code == 200
    assert response.json()["intent"] == "Agendamento"
    assert response.json()["provider"] == "fallback"


def test_leads_are_listed_with_admin_token(tmp_path, monkeypatch):
    import app as module
    leads_file = tmp_path / "leads.jsonl"
    monkeypatch.setattr(module, "LEADS_FILE", leads_file)
    monkeypatch.setenv("ATENDEAI_ADMIN_TOKEN", "test-token")
    created = client.post("/api/leads", json={
        "profile": "clinic", "name": "Ana", "phone": "+5511999999999", "interest": "avaliação"
    })
    assert created.status_code == 200
    assert client.get("/api/leads").status_code == 401
    listed = client.get("/api/leads", headers={"X-Admin-Token": "test-token"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
