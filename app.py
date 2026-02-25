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
    """Simula la validazione di un voucher senza riscattarlo."""
    url = f"{BASE_URL}/redemptions/validate"
    payload = {
        "customer": {"source_id": customer_email.strip()},
        "order": {"amount": int(float(order_amount) * 100)},
        "voucher": code.strip()
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

def get_voucher_info(code):
    """Ottiene i dettagli di un singolo codice e la sua campagna."""
    url = f"{BASE_URL}/vouchers/{code.strip()}"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

def get_campaign_info(name):
    """Dati generali e metadata della campagna."""
    url = f"{BASE_URL}/campaigns/{name.strip()}"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

def get_campaign_validation_rules(name):
    """Recupera i limiti di utilizzo per cliente (per_customer_limit)."""
    url = f"{BASE_URL}/campaigns/{name.strip()}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200: return f"Errore: {res.text}"
    
    data = res.json()
    assignments = data.get("validation_rules_assignments", {}).get("data", [])
    per_customer_limit = None

    for item in assignments:
        rid = item.get("rule_id")
        if rid:
            r_res = requests.get(f"{BASE_URL}/validation-rules/{rid}", headers=HEADERS)
            if r_res.status_code == 200:
                rule = r_res.json()
                for _, r_val in rule.get("rules", {}).items():
                    if isinstance(r_val, dict) and r_val.get("name") == "redemption.count.per_customer":
                        per_customer_limit = r_val.get("conditions", {}).get("$less_than_or_equal", [None])[0]

    if per_customer_limit is None:
        per_customer_limit = data.get("voucher", {}).get("redemption", {}).get("quantity")
    
    return {"per_customer_limit": per_customer_limit}

def get_campaign_redemptions(name):
    """Statistiche di utilizzo filtrate per la campagna specifica."""
    url = f"{BASE_URL}/redemptions?campaign_name={name.strip()}&limit=100"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200: return f"Errore: {res.text}"
    data = res.json()
    reds = data.get("redemptions", [])
    
    # Filtro client-side per sicurezza
    camp_reds = [r for r in reds if r.get("voucher", {}).get("campaign") == name.strip()]
    successful = len([r for r in camp_reds if r.get("result") == "SUCCESS" and r.get("status") == "SUCCEEDED"])
    failed = len([r for r in camp_reds if r.get("result") == "FAILURE"])
    
    return {"total": data.get("total", 0), "successful": successful, "failed": failed}

def get_campaign_vouchers(name):
    """Conta i voucher totali generati."""
    url = f"{BASE_URL}/campaigns/{name.strip()}/vouchers?limit=5"
    res = requests.get(url, headers=HEADERS)
    data = res.json() if res.status_code == 200 else {}
    return {"total_vouchers": data.get("total", 0)}

def list_campaigns():
    """Lista delle campagne disponibili."""
    url = f"{BASE_URL}/campaigns?limit=20"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

def debug_campaign(name):
    """Funzione per il JSON grezzo nel sidebar."""
    url = f"{BASE_URL}/campaigns/{name.strip()}"
    res = requests.get(url, headers=HEADERS)
    c_data = res.json() if res.status_code == 200 else {}
    return {"campaign_raw": c_data}

# --- AGENTE ---

def run_conversation(user_prompt, chat_history):
    system_prompt = """Sei l'assistente ufficiale PhotoSì per Voucherify. 

REGOLE COMPORTAMENTALI:
1. Se l'utente scrive un CODICE VOUCHER (stringa maiuscola), chiama 'get_voucher_info' per trovare la campagna.
2. Una volta trovata la campagna (o se l'utente dà il nome), chiama SEMPRE:
   - get_campaign_info
   - get_campaign_validation_rules
   - get_campaign_redemptions
   - get_campaign_vouchers
3. Se l'utente chiede un troubleshooting (es. 'perché non funziona?'), usa 'validate_voucher_simulation'.

FORMATO RISPOSTA OBBLIGATORIO:
📅 Quando posso richiedere il codice promo?
Dal [created_at] al [expiration_date]

🎁 Cosa prevede la promo?
[Sconto] su ordine minimo [min_amount], non cumulabile.

🛍️ Per quali prodotti è valido il codice?
[metadata.longDescription.IT]

📱 Posso ordinare sia da app che dal sito?
Sì, sia da app che dal sito PhotoSì.

🔁 Quante volte posso usare il codice?
[per_customer_limit] volte per cliente.

📊 Stato della campagna
- [Attiva ✅ / Scaduta ⚠️]
- Codici generati: [total_vouchers]
- Successi: [successful] / Falliti: [failed]

🌍 Lingue disponibili
[Elenco lingue da metadata]

Tono: Professionale e cordiale."""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history[:-1]: messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})

    tools = [
        {"type": "function", "function": {"name": "validate_voucher_simulation", "description": "Simula validazione carrello", "parameters": {"type": "object", "properties": {"code": {"type": "string"}, "customer_email": {"type": "string"}, "order_amount": {"type": "number"}}, "required": ["code", "customer_email", "order_amount"]}}},
        {"type": "function", "function": {"name": "get_voucher_info", "description": "Info su singolo codice", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
        {"type": "function", "function": {"name": "get_campaign_info", "description": "Dati campagna", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {"name": "get_campaign_validation_rules", "description": "Limiti per cliente", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {"name": "get_campaign_redemptions", "description": "Successi e fallimenti", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {"name": "get_campaign_vouchers", "description": "Conteggio voucher", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {"name": "list_campaigns", "description": "Lista campagne", "parameters": {"type": "object", "properties": {}}}},
    ]

    for _ in range(8):
        response = client.chat.completions.create(model="gpt-4o", messages=messages, tools=tools)
        msg = response.choices[0].message
        if not msg.tool_calls: return msg.content

        messages.append(msg)
        for tool in msg.tool_calls:
            fn = tool.function.name
            args = json.loads(tool.function.arguments)
            if fn == "validate_voucher_simulation": r = validate_voucher_simulation(args["code"], args["customer_email"], args["order_amount"])
            elif fn == "get_voucher_info": r = get_voucher_info(args["code"])
            elif fn == "get_campaign_info": r = get_campaign_info(args["name"])
            elif fn == "get_campaign_validation_rules": r = get_campaign_validation_rules(args["name"])
            elif fn == "get_campaign_redemptions": r = get_campaign_redemptions(args["name"])
            elif fn == "get_campaign_vouchers": r = get_campaign_vouchers(args["name"])
            elif fn == "list_campaigns": r = list_campaigns()
            messages.append({"tool_call_id": tool.id, "role": "tool", "name": fn, "content": json.dumps(r, ensure_ascii=False)})

    return "Errore di risposta."

# --- INTERFACCIA ---
st.set_page_config(page_title="Voucherify Full Agent", layout="wide")
st.title("🎫 PhotoSì - Voucherify Full Control")

if "h" not in st.session_state: st.session_state.h = []
for m in st.session_state.h:
    with st.chat_message(m["role"]): st.markdown(m["content"])

if p := st.chat_input("Nome campagna, codice voucher o simulazione..."):
    st.session_state.h.append({"role": "user", "content": p})
    with st.chat_message("user"): st.markdown(p)
    with st.chat_message("assistant"):
        ans = run_conversation(p, st.session_state.h)
        st.markdown(ans)
        st.session_state.h.append({"role": "assistant", "content": ans})

with st.sidebar:
    st.header("🔧 Debug")
    dbg_name = st.text_input("Campagna per JSON")
    if st.button("Mostra JSON") and dbg_name: st.json(debug_campaign(dbg_name))
