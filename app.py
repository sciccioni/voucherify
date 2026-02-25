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

# --- FUNZIONI VOUCHERIFY ---
def get_campaign_info(name):
    url = f"{BASE_URL}/campaigns/{name.strip()}"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

def get_campaign_validation_rules(name):
    url = f"{BASE_URL}/campaigns/{name.strip()}"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        return f"Errore: {res.text}"

    campaign_data = res.json()
    assignments = campaign_data.get("validation_rules_assignments", {}).get("data", [])

    rules_detail = []
    per_customer_limit = None

    for item in assignments:
        rule_id = item.get("rule_id")
        if rule_id:
            rule_url = f"{BASE_URL}/validation-rules/{rule_id}"
            rule_res = requests.get(rule_url, headers=HEADERS)
            if rule_res.status_code == 200:
                rule = rule_res.json()
                rules_detail.append(rule)
                for rule_key, rule_val in rule.get("rules", {}).items():
                    if isinstance(rule_val, dict):
                        if rule_val.get("name") == "redemption.count.per_customer":
                            conditions = rule_val.get("conditions", {})
                            limit = conditions.get("$less_than_or_equal", [None])[0]
                            if limit is not None:
                                per_customer_limit = limit

    if per_customer_limit is None:
        per_customer_limit = campaign_data.get("voucher", {}).get("redemption", {}).get("quantity")

    return {
        "assignments": assignments,
        "rules_detail": rules_detail,
        "per_customer_limit": per_customer_limit
    }

def get_campaign_redemptions(name):
    url = f"{BASE_URL}/redemptions?campaign_name={name.strip()}&limit=100"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        return f"Errore: {res.text}"
    data = res.json()
    redemptions = data.get("redemptions", [])
    
    # Filtra per campaign name anche lato client come fallback
    campaign_redemptions = [
        r for r in redemptions 
        if r.get("voucher", {}).get("campaign") == name.strip()
        or r.get("voucher", {}).get("campaign_id") in [
            a.get("related_object_id") for a in redemptions
        ]
    ]
    
    # Conta per tipo escludendo rollback
    successful = len([r for r in redemptions 
                      if r.get("result") == "SUCCESS" 
                      and r.get("object") == "redemption"
                      and r.get("status") == "SUCCEEDED"])
    failed = len([r for r in redemptions 
                  if r.get("result") == "FAILURE"])
    rolled_back = len([r for r in redemptions 
                       if r.get("status") == "ROLLED_BACK"])
    
    return {
        "total_redemptions": data.get("total", 0),
        "successful": successful,
        "failed": failed,
        "rolled_back": rolled_back,
        "warning": "I dati potrebbero includere redemptions di altre campagne se il filtro API non funziona correttamente"
    }

def get_campaign_vouchers(name):
    url = f"{BASE_URL}/campaigns/{name.strip()}/vouchers?limit=5"
    res = requests.get(url, headers=HEADERS)
    if res.status_code != 200:
        return f"Errore: {res.text}"
    data = res.json()
    vouchers = data.get("vouchers", [])
    return {
        "total_vouchers": data.get("total", 0),
        "sample_codes": [v.get("code") for v in vouchers[:5]]
    }

def list_campaigns():
    url = f"{BASE_URL}/campaigns?limit=20"
    res = requests.get(url, headers=HEADERS)
    return res.json() if res.status_code == 200 else f"Errore: {res.text}"

def debug_campaign(name):
    url = f"{BASE_URL}/campaigns/{name.strip()}"
    res = requests.get(url, headers=HEADERS)
    campaign_data = res.json() if res.status_code == 200 else {}

    assignments = campaign_data.get("validation_rules_assignments", {}).get("data", [])
    rules_detail = []
    per_customer_limit = None

    for item in assignments:
        rule_id = item.get("rule_id")
        if rule_id:
            rule_url = f"{BASE_URL}/validation-rules/{rule_id}"
            rule_res = requests.get(rule_url, headers=HEADERS)
            if rule_res.status_code == 200:
                rule = rule_res.json()
                rules_detail.append(rule)
                for rule_key, rule_val in rule.get("rules", {}).items():
                    if isinstance(rule_val, dict):
                        if rule_val.get("name") == "redemption.count.per_customer":
                            conditions = rule_val.get("conditions", {})
                            limit = conditions.get("$less_than_or_equal", [None])[0]
                            if limit is not None:
                                per_customer_limit = limit

    if per_customer_limit is None:
        per_customer_limit = campaign_data.get("voucher", {}).get("redemption", {}).get("quantity")

    redemptions_url = f"{BASE_URL}/redemptions?campaign_name={name.strip()}&limit=100"
    redemptions_res = requests.get(redemptions_url, headers=HEADERS)
    redemptions_data = redemptions_res.json() if redemptions_res.status_code == 200 else {}

    vouchers_url = f"{BASE_URL}/campaigns/{name.strip()}/vouchers?limit=5"
    vouchers_res = requests.get(vouchers_url, headers=HEADERS)
    vouchers_data = vouchers_res.json() if vouchers_res.status_code == 200 else {}

    return {
        "campaign": campaign_data,
        "assignments": assignments,
        "rules_detail": rules_detail,
        "per_customer_limit": per_customer_limit,
        "redemptions": redemptions_data,
        "vouchers": vouchers_data
    }

# --- AGENTE ---
def run_conversation(user_prompt, chat_history):
    system_prompt = """Sei un assistente di supporto clienti per PhotoSì, esperto delle campagne promozionali Voucherify.

Quando l'utente chiede info su una campagna, chiama SEMPRE tutte e 4 le funzioni:
1. get_campaign_info
2. get_campaign_validation_rules
3. get_campaign_redemptions
4. get_campaign_vouchers

Rispondi SEMPRE in questo formato:

📅 Quando posso richiedere il codice promo?
Dal [created_at formattata] al [expiration_date formattata] (con validità dei codici fino al [expiration_date formattata])

🎁 Cosa prevede la promo?
[sconto da discount.percent_off o amount_off] su ordine minimo [minimumOrderValue] euro, spese di spedizione escluse, non cumulabile con altre promo
(usa metadata.labelPromo.IT come etichetta breve es. "-30%")

🛍️ Per quali prodotti è valido il codice?
Usa metadata.longDescription.IT per descrivere i prodotti validi

📱 Posso ordinare sia da app che dal sito?
Sì, sia da app che dal sito PhotoSì

🔁 Quante volte posso usare il codice?
Usa il campo per_customer_limit da get_campaign_validation_rules:
- Se è un numero: "Il codice può essere utilizzato massimo [N] volte per cliente"
- Se è null: "Non specificato"

⏳ Entro quanto è valido il codice?
Il codice sarà valido entro il [expiration_date formattata come GG mese AAAA]

📊 Stato della campagna
- La campagna è attualmente: [Attiva ✅ / Scaduta ⚠️] (da campo active)
- Categoria: [category] (es. "Exclusive - non stackable" significa non cumulabile)
- Codici totali generati: [vouchers_count]
- Codici già utilizzati: [total_redemptions da get_campaign_redemptions]
- Utilizzi andati a buon fine: [successful]
- Utilizzi falliti: [failed]

🌍 La promo è disponibile anche in altre lingue?
Sì, la promo è disponibile in: Italiano, Inglese, Tedesco, Francese, Spagnolo, Olandese
(elenca solo le lingue per cui esiste metadata.longDescription)

Regole importanti:
- Chiama SEMPRE tutte e 4 le funzioni prima di rispondere
- Il campo per_customer_limit è già estratto, usalo direttamente
- NON mostrare mai JSON grezzo
- Date sempre in formato: GG mese AAAA (es. 30 novembre 2025)
- Se expiration_date è assente scrivi "Nessuna scadenza impostata"
- Se la campagna è scaduta aggiungi ⚠️ CAMPAGNA SCADUTA in cima alla risposta
- Se l'utente non conosce il nome usa list_campaigns
- Rispondi sempre in italiano
- Mantieni un tono cordiale e professionale da supporto clienti"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in chat_history[:-1]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_campaign_info",
                "description": "Ottieni tutti i dettagli di una campagna specifica da Voucherify",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_campaign_validation_rules",
                "description": "Recupera le validation rules. Restituisce per_customer_limit con il numero massimo di utilizzi per cliente",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_campaign_redemptions",
                "description": "Recupera lo storico utilizzi della campagna: totale, riusciti e falliti",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_campaign_vouchers",
                "description": "Recupera il numero totale di voucher generati per la campagna",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_campaigns",
                "description": "Elenca tutte le campagne disponibili su Voucherify",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]

    for _ in range(8):
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        if not tool_calls:
            return response_message.content

        messages.append(response_message)
        for tool_call in tool_calls:
            function_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            if function_name == "get_campaign_info":
                result = get_campaign_info(args.get("name"))
            elif function_name == "get_campaign_validation_rules":
                result = get_campaign_validation_rules(args.get("name"))
            elif function_name == "get_campaign_redemptions":
                result = get_campaign_redemptions(args.get("name"))
            elif function_name == "get_campaign_vouchers":
                result = get_campaign_vouchers(args.get("name"))
            elif function_name == "list_campaigns":
                result = list_campaigns()
            else:
                result = {"error": "Funzione non trovata"}
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": json.dumps(result, ensure_ascii=False),
            })

    return "Non sono riuscito a recuperare le informazioni. Riprova."


# --- INTERFACCIA STREAMLIT ---
st.set_page_config(page_title="Voucherify Agent", page_icon="🎫", layout="centered")
st.title("🎫 PhotoSì - Voucherify Agent")
st.caption("Chiedimi info su qualsiasi campagna promozionale")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Es: Dimmi tutto sulla campagna COMARKETING_TUM_SETT2025_3..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Interrogando Voucherify..."):
            answer = run_conversation(prompt, st.session_state.chat_history)
            st.markdown(answer)
            st.session_state.chat_history.append({"role": "assistant", "content": answer})

# --- DEBUG SIDEBAR ---
with st.sidebar:
    st.header("🔧 Debug JSON")
    st.caption("Mostra il JSON grezzo per verificare i campi restituiti da Voucherify")
    campaign_debug = st.text_input("Nome campagna")
    if st.button("Mostra JSON grezzo") and campaign_debug:
        with st.spinner("Caricamento..."):
            raw = debug_campaign(campaign_debug)
            st.json(raw)
