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

                # CASO 1: limite nelle validation rules (es. COMARKETING)
                for rule_key, rule_val in rule.get("rules", {}).items():
                    if isinstance(rule_val, dict):
                        if rule_val.get("name") == "redemption.count.per_customer":
                            conditions = rule_val.get("conditions", {})
                            limit = conditions.get("$less_than_or_equal", [None])[0]
                            if limit is not None:
                                per_customer_limit = limit

    # CASO 2: limite in voucher.redemption.quantity (es. TEST_SHIPPING)
    if per_customer_limit is None:
        per_customer_limit = campaign_data.get("voucher", {}).get("redemption", {}).get("quantity")

    return {
        "assignments": assignments,
        "rules_detail": rules_detail,
        "per_customer_limit": per_customer_limit
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

    return {
        "campaign": campaign_data,
        "assignments": assignments,
        "rules_detail": rules_detail,
        "per_customer_limit": per_customer_limit
    }

# --- AGENTE ---
def run_conversation(user_prompt, chat_history):
    system_prompt = """Sei un assistente di supporto clienti per PhotoSì, esperto delle campagne promozionali Voucherify.

Quando l'utente chiede info su una campagna, chiama SEMPRE sia get_campaign_info che get_campaign_validation_rules.

Rispondi SEMPRE in questo formato:

📅 Quando posso richiedere il codice promo?
Dal [start_date] al [expiration_date] (con validità dei codici fino al [expiration_date])

🎁 Cosa prevede la promo?
[sconto] su ordine minimo [minimumOrderValue] euro, spese di spedizione escluse, non cumulabile con altre promo

🛍️ Per quali prodotti è valido il codice?
Usa il campo metadata.longDescription.IT per descrivere i prodotti validi

📱 Posso ordinare sia da app che dal sito?
Sì, sia da app che dal sito PhotoSì

🔁 Quante volte posso usare il codice?
Leggi il campo "per_customer_limit" restituito da get_campaign_validation_rules:
- Se è un numero: "Il codice può essere utilizzato massimo [N] volte per cliente"
- Se è null o mancante: "Non specificato"

⏳ Entro quanto è valido il codice?
Il codice sarà valido entro il [expiration_date formattata come GG mese AAAA]

Regole importanti:
- Chiama SEMPRE entrambe le funzioni
- Il campo per_customer_limit è già estratto, usalo direttamente senza cercare nel JSON
- NON mostrare mai JSON grezzo
- Date sempre in formato: GG mese AAAA (es. 30 novembre 2025)
- Se la campagna è scaduta aggiungi ⚠️ CAMPAGNA SCADUTA in cima
- Se l'utente non conosce il nome della campagna usa list_campaigns
- Rispondi sempre in italiano"""

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
                    "properties": {"name": {"type": "string", "description": "Nome o ID della campagna"}},
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_campaign_validation_rules",
                "description": "Recupera le validation rules di una campagna. Restituisce per_customer_limit con il numero massimo di utilizzi per cliente",
                "parameters": {
                    "type": "object",
                    "properties": {"name": {"type": "string", "description": "Nome o ID della campagna"}},
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

    for _ in range(5):
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
