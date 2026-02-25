import streamlit as st
import requests
import json
from openai import OpenAI

# --- CONFIGURAZIONE ---
try:
    V_ID = st.secrets["VOUCHERIFY_APP_ID"]
    V_KEY = st.secrets["VOUCHERIFY_SECRET_KEY"]
    O_KEY = st.secrets["OPENAI_API_KEY"]
except Exception as e:
    st.error("Mancano le chiavi nei Secrets di Streamlit!")
    st.stop()

client = OpenAI(api_key=O_KEY)
HEADERS = {"X-App-Id": V_ID, "X-App-Token": V_KEY, "Content-Type": "application/json"}
BASE_URL = "https://api.voucherify.io/v1"

# --- FUNZIONI VOUCHERIFY (TOOLS) ---

def validate_voucher_simulation(code, customer_email, order_amount):
    """Simula la validazione di un voucher per un cliente e un importo specifici."""
    url = f"{BASE_URL}/redemptions/validate"
    payload = {
        "customer": {"source_id": customer_email.strip()},
        "order": {"amount": int(float(order_amount) * 100)}, # Conversione in centesimi
        "voucher": code.strip()
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    return res.json() if res.status_code == 200 else f"Errore validazione: {res.text}"

def get_voucher_info(code):
    """Ottiene i dettagli di un singolo voucher."""
    url = f"{BASE_URL}/vouchers/{code.strip()}"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

def get_campaign_info(name):
    """Ottiene i dati generali della campagna."""
    url = f"{BASE_URL}/campaigns/{name.strip()}"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

def get_campaign_redemptions(name):
    """Recupera le statistiche di utilizzo con filtro di sicurezza."""
    url = f"{BASE_URL}/redemptions?campaign_name={name.strip()}&limit=100"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200: return f"Errore: {res.text}"
    data = res.json()
    redemptions = data.get("redemptions", [])
    
    # Conteggio granulare
    successful = len([r for r in redemptions if r.get("result") == "SUCCESS" and r.get("status") == "SUCCEEDED"])
    failed = len([r for r in redemptions if r.get("result") == "FAILURE"])
    
    return {
        "total": data.get("total", 0),
        "successful": successful,
        "failed": failed
    }

def list_campaigns():
    """Elenca le ultime campagne."""
    url = f"{BASE_URL}/campaigns?limit=20"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

# --- LOGICA AGENTE ---

def run_conversation(user_prompt, chat_history):
    system_prompt = """Sei un assistente esperto PhotoSì per Voucherify.

REGOLE DI TROUBLESHOOTING:
Se l'utente segnala un problema con un codice o chiede se è valido, usa SEMPRE 'validate_voucher_simulation'.
Se l'importo o l'email non sono forniti, chiedili cortesemente per procedere alla simulazione.

FORMATO RISPOSTA CAMPAGNA:
📅 Validità: [created_at] - [expiration_date]
🎁 Promo: [Sconto] su min. [ordine]
🛍️ Prodotti: [metadata.longDescription.IT]
🔁 Limiti: [per_customer_limit]
📊 Stato: [Successi/Fallimenti]

Importante: Rispondi in italiano con tono professionale."""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history[:-1]: messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})

    tools = [
        {"type": "function", "function": {"name": "validate_voucher_simulation", "description": "Verifica se un voucher è applicabile a un carrello", "parameters": {"type": "object", "properties": {"code": {"type": "string"}, "customer_email": {"type": "string"}, "order_amount": {"type": "number"}}, "required": ["code", "customer_email", "order_amount"]}}},
        {"type": "function", "function": {"name": "get_voucher_info", "description": "Info su un singolo codice", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
        {"type": "function", "function": {"name": "get_campaign_info", "description": "Dettagli campagna", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {"name": "get_campaign_redemptions", "description": "Statistiche redemptions", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {"name": "list_campaigns", "description": "Lista campagne", "parameters": {"type": "object", "properties": {}}}},
    ]

    for _ in range(5):
        response = client.chat.completions.create(model="gpt-4o", messages=messages, tools=tools)
        msg = response.choices[0].message
        if not msg.tool_calls: return msg.content

        messages.append(msg)
        for tool in msg.tool_calls:
            fn = tool.function.name
            args = json.loads(tool.function.arguments)
            
            if fn == "validate_voucher_simulation": res = validate_voucher_simulation(args["code"], args["customer_email"], args["order_amount"])
            elif fn == "get_voucher_info": res = get_voucher_info(args["code"])
            elif fn == "get_campaign_info": res = get_campaign_info(args["name"])
            elif fn == "get_campaign_redemptions": res = get_campaign_redemptions(args["name"])
            elif fn == "list_campaigns": res = list_campaigns()
            
            messages.append({"tool_call_id": tool.id, "role": "tool", "name": fn, "content": json.dumps(res, ensure_ascii=False)})

    return "Errore di elaborazione."

# --- UI STREAMLIT ---
st.set_page_config(page_title="Voucherify Pro Agent", layout="centered")
st.title("🎫 PhotoSì - Voucherify Pro")

if "history" not in st.session_state: st.session_state.history = []
for m in st.session_state.history:
    with st.chat_message(m["role"]): st.markdown(m["content"])

if prompt := st.chat_input("Es: Il codice PROMO10 è valido per mario@test.it con 30€?"):
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"): st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Analisi Voucherify in corso..."):
            ans = run_conversation(prompt, st.session_state.history)
            st.markdown(ans)
            st.session_state.history.append({"role": "assistant", "content": ans})
