from pathlib import Path
import json
import os
import re
import secrets
import urllib.request
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).parent
LEADS_FILE = BASE_DIR / "data" / "leads.jsonl"

app = FastAPI(title="AtendeAI Demo", version="0.2.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

PROFILES = {
    "clinic": {"label":"Clínica odontológica", "name":"Clínica Sorriso Vivo", "accent":"Saúde e bem-estar", "services":["avaliação","limpeza","clareamento","aparelho"], "goal":"agendar uma avaliação", "questions":["Qual serviço você procura?","Você prefere manhã ou tarde?"], "opening":"Olá! Sou a assistente da Clínica Sorriso Vivo. Posso explicar nossos tratamentos e encontrar um horário para sua avaliação."},
    "real_estate": {"label":"Imobiliária", "name":"Prime Lar Imóveis", "accent":"Compra e aluguel", "services":["compra","aluguel","visita","avaliação de imóvel"], "goal":"qualificar o interesse e agendar uma visita", "questions":["Você busca comprar ou alugar?","Em qual bairro e faixa de valor?"], "opening":"Olá! Sou a assistente da Prime Lar Imóveis. Posso ajudar a encontrar imóveis e agendar uma visita."},
    "auto": {"label":"Oficina automotiva", "name":"Oficina Torque Certo", "accent":"Manutenção sem surpresa", "services":["revisão","freios","troca de óleo","diagnóstico"], "goal":"entender o problema e reservar um horário", "questions":["Qual é o modelo do veículo?","O problema apareceu quando?"], "opening":"Olá! Sou a assistente da Oficina Torque Certo. Posso entender o problema do seu carro e verificar um horário para atendimento."},
}
CUSTOM_PROFILES = {}

class ChatRequest(BaseModel):
    profile: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    history: list[dict] = Field(default_factory=list, max_length=20)

class LeadRequest(BaseModel):
    profile: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=8, max_length=30)
    interest: str = Field(min_length=2, max_length=300)

class CustomizeRequest(BaseModel):
    business_name: str = Field(min_length=2, max_length=100)
    segment: str = Field(min_length=2, max_length=80)
    city: str = Field(default="", max_length=80)
    services: list[str] = Field(min_length=1, max_length=8)
    goal: str = Field(min_length=2, max_length=160)

def get_profile(profile_id: str):
    profile = PROFILES.get(profile_id) or CUSTOM_PROFILES.get(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")
    return profile

def detect_intent(message: str, profile: dict) -> str:
    text = message.lower()
    if any(word in text for word in ("preço","valor","quanto","orçamento")): return "Solicitação de preço"
    if any(word in text for word in ("agendar","marcar","horário","visita")): return "Agendamento"
    if any(word in text for word in ("problema","defeito","dor","urgente")): return "Problema para avaliação"
    if any(service.lower() in text for service in profile["services"]): return "Interesse em serviço"
    return "Dúvida inicial"

def fallback_answer(profile: dict, message: str, history: list[dict]) -> dict:
    intent = detect_intent(message, profile)
    text = message.lower()
    if any(word in text for word in ("agendar","marcar","horário","visita")):
        reply = f"Claro. Para {profile['goal']}, preciso saber seu nome e um telefone. Depois nossa equipe confirma o melhor horário."
        action = "Solicitar contato e encaminhar para agenda"
    elif any(word in text for word in ("preço","valor","quanto","orçamento")):
        reply = f"Posso preparar uma estimativa. Qual serviço você procura? Trabalhamos com {', '.join(profile['services'][:-1])} e {profile['services'][-1]}."
        action = "Qualificar serviço antes de enviar orçamento"
    elif any(word in text for word in ("oi","olá","ola","bom dia","boa tarde")) and not history:
        reply, action = profile["opening"], "Apresentar opções"
    else:
        reply = f"Entendi. Posso ajudar com {', '.join(profile['services'][:-1])} ou {profile['services'][-1]}. {profile['questions'][0]}"
        action = "Fazer pergunta de qualificação"
    return {"reply":reply,"intent":intent,"next_action":action,"lead_score":"quente" if intent in ("Agendamento","Solicitação de preço") else "morno","provider":"fallback"}

def llm_answer(profile: dict, message: str, history: list[dict]):
    key = os.getenv("OPENROUTER_API_KEY")
    if not key: return None
    prompt = ("Você é um agente comercial. Responda em português brasileiro, de forma curta e útil. "
              f"Negócio: {profile['name']}. Serviços: {', '.join(profile['services'])}. Objetivo: {profile['goal']}. "
              "Nunca invente preços, horários ou disponibilidade. Retorne SOMENTE JSON com as chaves reply, intent, next_action, lead_score."
              )
    body = json.dumps({"model":os.getenv("ATENDEAI_MODEL","google/gemma-4-26b-a4b-it:free"),"messages":[{"role":"system","content":prompt},{"role":"user","content":message}],"temperature":0.2,"max_tokens":250}).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body, headers={"Authorization":f"Bearer {key}","Content-Type":"application/json","HTTP-Referer":"http://localhost:8088","X-Title":"AtendeAI"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read())
        content = data["choices"][0]["message"]["content"].strip().replace("```json","").replace("```","").strip()
        result = json.loads(content)
        result["provider"] = "openrouter"
        return result
    except (OSError, KeyError, IndexError, json.JSONDecodeError, TypeError):
        return None

def profiles_public():
    return {key:{k:v for k,v in value.items() if k != "questions"} for key,value in {**PROFILES,**CUSTOM_PROFILES}.items()}

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

@app.get("/")
def index(): return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/health")
def health(): return {"status":"ok","service":"atendeai-demo","version":"0.2.0"}

@app.get("/api/profiles")
def profiles(): return profiles_public()

@app.post("/api/customize")
def customize(payload: CustomizeRequest):
    profile_id = "custom_" + secrets.token_urlsafe(8)
    services = [service.strip() for service in payload.services if service.strip()]
    profile = {"label":payload.segment.strip(),"name":payload.business_name.strip(),"accent":payload.city.strip() or payload.segment.strip(),"services":services,"goal":payload.goal.strip(),"questions":[f"Qual serviço de {payload.business_name.strip()} você procura?","Qual é a melhor forma de contato?"],"opening":f"Olá! Sou a assistente da {payload.business_name.strip()}. Posso ajudar com {', '.join(services)} e {payload.goal.strip()}."}
    CUSTOM_PROFILES[profile_id] = profile
    return {"profile_id":profile_id,"profile":{k:v for k,v in profile.items() if k != "questions"}}

@app.post("/api/chat")
def chat(payload: ChatRequest):
    profile = get_profile(payload.profile)
    return llm_answer(profile, payload.message, payload.history) or fallback_answer(profile, payload.message, payload.history)

@app.post("/api/leads")
def leads(payload: LeadRequest):
    normalized_phone = re.sub(r"[^0-9+() -]", "", payload.phone).strip()
    record = {"created_at":datetime.now(timezone.utc).isoformat(),"profile":payload.profile,"name":payload.name.strip(),"phone":normalized_phone,"interest":payload.interest.strip()}
    LEADS_FILE.parent.mkdir(exist_ok=True)
    with LEADS_FILE.open("a",encoding="utf-8") as file: file.write(json.dumps(record,ensure_ascii=False)+"\n")
    return {"ok":True,"message":"Lead registrado. Em uma implantação real, a equipe entraria em contato."}

@app.get("/api/leads")
def list_leads(x_admin_token: str | None = Header(default=None)):
    expected = os.getenv("ATENDEAI_ADMIN_TOKEN")
    if not expected or not secrets.compare_digest(x_admin_token or "", expected): raise HTTPException(status_code=401, detail="Não autorizado")
    items = []
    if LEADS_FILE.exists():
        for line in LEADS_FILE.read_text(encoding="utf-8").splitlines():
            try: items.append(json.loads(line))
            except json.JSONDecodeError: continue
    return {"data":list(reversed(items[-100:])),"total":len(items)}
