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

def get_voucher_info(code):
    """Cerca dettagli di un singolo codice. Se fallisce, restituisce l'errore per far provare l'altro tool."""
    url = f"{BASE_URL}/vouchers/{code.strip()}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    return {"error": "Voucher non trovato", "status": res.status_code}

def get_campaign_info(name):
    """Ottiene i dati generali della campagna."""
    url = f"{BASE_URL}/campaigns/{name.strip()}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code == 200:
        return res.json()
    return {"error": "Campagna non trovata", "status": res.status_code}

def get_campaign_validation_rules(name):
    """Estrae i limiti di utilizzo per cliente analizzando le regole associate."""
    url = f"{BASE_URL}/campaigns/{name.strip()}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200: return {"error": "Non trovata"}
    
    data = res.json()
    assignments = data.get("validation_rules_assignments", {}).get("data", [])
    per_customer_limit = None

    for item in assignments:
        rid = item.get("rule_id")
        if rid:
            r_res = requests.get(f"{BASE_URL}/validation-rules/{rid}", headers=HEADERS)
            if r_res.status_code == 200:
                rule = r_res.json()
                # Cerchiamo la regola specifica nel dizionario delle regole
                for r_key, r_val in rule.get("rules", {}).items():
                    if isinstance(r_val, dict) and r_val.get("name") == "redemption.count.per_customer":
                        conditions = r_val.get("conditions", {})
                        limit = conditions.get("$less_than_or_equal", [None])[0]
                        if limit is not None: per_customer_limit = limit

    if per_customer_limit is None:
        per_customer_limit = data.get("voucher", {}).get("redemption", {}).get("quantity")
    
    return {"per_customer_limit": per_customer_limit}

def get_campaign_redemptions(name):
    """Statistiche di utilizzo con filtraggio lato client per evitare dati sporchi."""
    url = f"{BASE_URL}/redemptions?campaign_name={name.strip()}&limit=100"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200: return {"error": "Errore API"}
    data = res.json()
    reds = data.get("redemptions", [])
    
    # Filtro rigoroso: controlliamo sia il nome che l'ID della campagna nel voucher
    camp_reds = [r for r in reds if 
                 r.get("voucher", {}).get("campaign") == name.strip() or 
                 r.get("voucher", {}).get("campaign_id") == name.strip()]
    
    successful = len([r for r in camp_reds if r.get("result") == "SUCCESS" and r.get("status") == "SUCCEEDED"])
    failed = len([r for r in camp_reds if r.get("result") == "FAILURE"])
    rolled_back = len([r for r in camp_reds if r.get("status") == "ROLLED_BACK"])
    
    return {
        "total_campaign_redemptions": len(camp_reds),
        "successful": successful, 
        "failed": failed,
        "rolled_back": rolled_back
    }

def get_campaign_vouchers(name):
    """Conteggio totale dei voucher generati per la campagna."""
    url = f"{BASE_URL}/campaigns/{name.strip()}/vouchers?limit=1"
    res = requests.get(url, headers=HEADERS)
    data = res.json() if res.status_code == 200 else {}
    return {"total_vouchers": data.get("total", 0)}

def validate_voucher_simulation(code, customer_email, order_amount):
    """Simula una validazione per troubleshooting."""
    url = f"{BASE_URL}/redemptions/validate"
    payload = {
        "customer": {"source_id": customer_email.strip()},
        "order": {"amount": int(float(order_amount) * 100)},
        "voucher": code.strip()
    }
    res = requests.post(url, headers=HEADERS, json=payload)
    return res.json()

# --- LOGICA AGENTE ---

def run_conversation(user_prompt, chat_history):
    system_prompt = """Sei un assistente esperto PhotoSì. Non inventare MAI dati. 

STRATEGIA DI RICERCA:
1. Se l'utente fornisce una stringa (es. CUSTOMER_5E_APR25_3):
   - Prova 'get_voucher_info'. 
   - Se restituisce errore o non trova nulla, prova IMMEDIATAMENTE 'get_campaign_info'.
2. Una volta identificata la campagna, chiama SEMPRE queste 4 funzioni per completare il quadro:
   - get_campaign_info
   - get_campaign_validation_rules
   - get_campaign_redemptions
   - get_campaign_vouchers

FORMATO RISPOSTA:
📅 Quando posso richiedere il codice promo?
Dal [created_at] al [expiration_date] (Validità codici fino al [expiration_date])

🎁 Cosa prevede la promo?
[Valore sconto] su ordine minimo [min_amount]€, non cumulabile.
(Usa metadata.labelPromo.IT se presente)

🛍️ Per quali prodotti è valido il codice?
[metadata.longDescription.IT]

📱 Posso ordinare sia da app che dal sito?
Sì, sia da app che dal sito PhotoSì.

🔁 Quante volte posso usare il codice?
- Se per_customer_limit è un numero: "Massimo [N] volte per cliente"
- Se è null: "Nessun limite impostato per cliente"

⏳ Entro quanto è valido il codice?
Il codice è valido entro il [expiration_date formattata GG mese AAAA]

📊 Stato della campagna
- Stato: [Attiva ✅ / Scaduta ⚠️]
- Codici generati: [total_vouchers]
- Utilizzi totali: [total_campaign_redemptions]
- Successi: [successful] / Falliti: [failed]

🌍 Lingue disponibili
Elenca le lingue basandoti sui campi metadata.longDescription disponibili (IT, EN, DE, ecc.)

REGOLE CRITICHE:
- Se expiration_date manca, scrivi "Nessuna scadenza".
- Se la campagna è scaduta, scrivi ⚠️ CAMPAGNA SCADUTA in cima.
- Se l'utente chiede un test, chiedi email e importo per 'validate_voucher_simulation'."""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history[:-1]: messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})

    tools = [
        {"type": "function", "function": {"name": "get_voucher_info", "description": "Info su singolo codice", "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}},
        {"type": "function", "function": {"name": "get_campaign_info", "description": "Info su campagna", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {"name": "get_campaign_validation_rules", "description": "Limiti utilizzo cliente", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {"name": "get_campaign_redemptions", "description": "Statistiche redemptions", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {"name": "get_campaign_vouchers", "description": "Conteggio voucher", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}},
        {"type": "function", "function": {"name": "validate_voucher_simulation", "description": "Simula validazione carrello", "parameters": {"type": "object", "properties": {"code": {"type": "string"}, "customer_email": {"type": "string"}, "order_amount": {"type": "number"}}, "required": ["code", "customer_email", "order_amount"]}}},
    ]

    for _ in range(10):
        response = client.chat.completions.create(model="gpt-4o", messages=messages, tools=tools)
        msg = response.choices[0].message
        if not msg.tool_calls: return msg.content

        messages.append(msg)
        for tool in msg.tool_calls:
            fn = tool.function.name
            args = json.loads(tool.function.arguments)
            if fn == "get_voucher_info": r = get_voucher_info(args["code"])
            elif fn == "get_campaign_info": r = get_campaign_info(args["name"])
            elif fn == "get_campaign_validation_rules": r = get_campaign_validation_rules(args["name"])
            elif fn == "get_campaign_redemptions": r = get_campaign_redemptions(args["name"])
            elif fn == "get_campaign_vouchers": r = get_campaign_vouchers(args["name"])
            elif fn == "validate_voucher_simulation": r = validate_voucher_simulation(args["code"], args["customer_email"], args["order_amount"])
            messages.append({"tool_call_id": tool.id, "role": "tool", "name": fn, "content": json.dumps(r, ensure_ascii=False)})

    return "Errore critico nella catena di funzioni."

# --- UI STREAMLIT ---
st.set_page_config(page_title="PhotoSì Voucherify Agent", layout="centered")
st.title("🎫 PhotoSì - Voucherify Agent")

if "chat_history" not in st.session_state: st.session_state.chat_history = []
for m in st.session_state.chat_history:
    with st.chat_message(m["role"]): st.markdown(m["content"])

if p := st.chat_input("Inserisci il nome della campagna o un codice..."):
    st.session_state.chat_history.append({"role": "user", "content": p})
    with st.chat_message("user"): st.markdown(p)
    with st.chat_message("assistant"):
        ans = run_conversation(p, st.session_state.chat_history)
        st.markdown(ans)
        st.session_state.chat_history.append({"role": "assistant", "content": ans})
