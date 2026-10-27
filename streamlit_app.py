"""
Streamlit Web Demo for Autonomous Customer Support Agent.
Connects with FastAPI backend endpoints:
- GET /health
- POST /login
- GET /orders
- POST /chat
- POST /confirm
- GET /audit
"""
import json
import requests
import streamlit as st

API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Team Logic - AI Customer Support Agent",
    page_icon="🤖",
    layout="wide"
)

# Initialize Session State
if "token" not in st.session_state:
    st.session_state.token = "cust_1"
if "customer_email" not in st.session_state:
    st.session_state.customer_email = "alice@example.com"
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "pending_change_request" not in st.session_state:
    st.session_state.pending_change_request = None


# Helper API caller
def api_request(method: str, path: str, json_data: dict = None):
    url = f"{API_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, timeout=5)
        else:
            resp = requests.post(url, headers=headers, json=json_data, timeout=5)
        return resp.status_code, resp.json()
    except Exception as e:
        return 500, {"error": f"Cannot connect to FastAPI backend at {API_BASE_URL}. Is it running? Details: {str(e)}"}


# Sidebar: Customer Profile & Backend Status
with st.sidebar:
    st.title("🤖 Team Logic")
    st.caption("Autonomous Customer Support Demo")
    st.markdown("---")
    
    st.subheader("Customer Session")
    st.write(f"👤 **Customer:** Alice Smith")
    st.write(f"📧 **Email:** `{st.session_state.customer_email}`")
    st.write(f"🔑 **Token:** `{st.session_state.token}`")
    
    st.markdown("---")
    st.subheader("Backend Status")
    status_code, health = api_request("GET", "/health")
    if status_code == 200:
        st.success(f"FastAPI Online (v{health.get('version', '1.0')})")
    else:
        st.warning("FastAPI Offline. Start backend with `uvicorn main:app --reload`")

    st.markdown("---")
    st.markdown(
        """
        **Sample prompts to test:**
        - `Change shipping address for order 10023 to 12 MG Road, Pune`
        - `Cancel order 10023`
        - `Track order 10023`
        - `Change shipping address for order 10024 to 55 Lake Road` *(blocked: already shipped)*
        """
    )


# Main Tabs
tab_chat, tab_orders, tab_audit = st.tabs(["💬 Chat & Guardrails", "📦 Orders", "🛡️ Audit Log"])

# ============================================================================
# TAB 1: Chat & Guardrails
# ============================================================================
with tab_chat:
    st.header("Conversational Order Support")
    st.write("Ask to change address, track, or cancel orders. The AI will preview changes and seek confirmation.")

    # Render Chat History
    for chat in st.session_state.chat_history:
        with st.chat_message(chat["role"]):
            st.markdown(chat["content"])
            if "trace" in chat and chat["trace"]:
                with st.expander("🔍 View Guardrail Trace"):
                    for step in chat["trace"]:
                        st.markdown(f"- **{step.get('node')}**: `{step.get('status')}`")

    # Render Pending Confirmation if any
    if st.session_state.pending_change_request:
        cr = st.session_state.pending_change_request
        st.warning("⚠️ **Confirmation Required:** Please review the proposed changes below before committing to database.")
        
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**Intent:** `{cr.get('intent')}`\n\n**Order:** `#{cr.get('order_id')}`\n\n**Proposed:** `{json.dumps(cr.get('proposed_change'))}`")
        with col2:
            st.markdown(f"**Current Value:** `{cr.get('preview', {}).get('current')}`")
            st.markdown(f"**New Value:** `{cr.get('preview', {}).get('new')}`")
            st.caption(f"Expires at: {cr.get('expires_at')}")

        btn_confirm, btn_cancel = st.columns([1, 1])
        with btn_confirm:
            if st.button("✅ Confirm & Apply", type="primary"):
                s_code, resp = api_request("POST", "/confirm", {
                    "request_id": cr["request_id"],
                    "action": "confirm",
                    "idempotency_key": cr["idempotency_key"]
                })
                if s_code == 200:
                    st.success(resp.get("message"))
                    st.session_state.chat_history.append({"role": "assistant", "content": f"✅ {resp.get('message')}"})
                else:
                    st.error(resp.get("detail", "Confirmation failed"))
                st.session_state.pending_change_request = None
                st.rerun()

        with btn_cancel:
            if st.button("❌ Decline Change"):
                s_code, resp = api_request("POST", "/confirm", {
                    "request_id": cr["request_id"],
                    "action": "cancel",
                    "idempotency_key": cr["idempotency_key"]
                })
                st.info(resp.get("message", "Change was cancelled."))
                st.session_state.chat_history.append({"role": "assistant", "content": f"❌ {resp.get('message')}"})
                st.session_state.pending_change_request = None
                st.rerun()

    # User Input
    user_input = st.chat_input("Type your order request (e.g., 'Change shipping address for order 10023 to 12 MG Road, Pune')...")
    if user_input:
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            status_code, resp = api_request("POST", "/chat", {"message": user_input})
            if status_code == 200:
                reply = resp.get("reply", "")
                st.markdown(reply)
                
                # Check if confirmation is required
                if resp.get("needs_confirmation") and resp.get("change_request"):
                    st.session_state.pending_change_request = resp["change_request"]
                
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": reply,
                    "trace": resp.get("trace", [])
                })
                st.rerun()
            else:
                err_msg = resp.get("detail", "Error communicating with support agent.")
                st.error(err_msg)
                st.session_state.chat_history.append({"role": "assistant", "content": f"⚠️ {err_msg}"})


# ============================================================================
# TAB 2: Orders
# ============================================================================
with tab_orders:
    st.header("Your Orders")
    st.caption("Live customer orders fetched from the database")
    
    if st.button("🔄 Refresh Orders"):
        st.rerun()

    s_code, orders = api_request("GET", "/orders")
    if s_code == 200 and isinstance(orders, list):
        for o in orders:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
                with col1:
                    st.subheader(f"Order #{o.get('order_ref')}")
                    st.caption(f"Order ID: {o.get('order_id')} | Version: {o.get('version')}")
                with col2:
                    status_val = o.get('status', '').upper()
                    if status_val == "PLACED":
                        st.info(f"Status: **{status_val}**")
                    elif status_val == "SHIPPED":
                        st.warning(f"Status: **{status_val}**")
                    elif status_val == "CANCELLED":
                        st.error(f"Status: **{status_val}**")
                    else:
                        st.success(f"Status: **{status_val}**")
                with col3:
                    st.markdown(f"**Total:** `${o.get('total_amount')}`")
                    st.caption(f"Delivery: {o.get('delivery_date')}")
                with col4:
                    st.markdown(f"**Shipping Address:**\n`{o.get('shipping_address')}`")

                # Show items
                items = o.get("items", [])
                if items:
                    with st.expander("📦 View Items in this Order"):
                        for it in items:
                            prod = it.get("product") or {}
                            st.write(f"- **{prod.get('name', 'Product')}** (Qty: {it.get('quantity')}) - `${it.get('item_price')}`")
    else:
        st.info("No orders found or backend is offline.")


# ============================================================================
# TAB 3: Audit Log
# ============================================================================
with tab_audit:
    st.header("Security & Compliance Audit Log")
    st.caption("Append-only audit trail with masked PII and rule evaluation")
    
    if st.button("🔄 Refresh Audit Log"):
        st.rerun()

    s_code, logs = api_request("GET", "/audit")
    if s_code == 200 and isinstance(logs, list):
        if not logs:
            st.info("No audit logs recorded yet. Try changing an address or cancelling an order.")
        else:
            for log in reversed(logs):
                dec = log.get("decision", "").upper()
                badge_type = "🟢" if dec == "APPROVED" else ("🔴" if dec == "BLOCKED" else "🟡")
                with st.container(border=True):
                    st.markdown(f"{badge_type} **Action:** `{log.get('action')}` | **Decision:** `{dec}` | **Order:** `#{log.get('order_id')}` | **Latency:** `{log.get('latency_ms')}ms`")
                    st.caption(f"Audit ID: {log.get('audit_id')} | Time: {log.get('created_at')}")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.write("**Before State (Masked):**", log.get("before_state"))
                    with c2:
                        st.write("**After State (Masked):**", log.get("after_state"))
    else:
        st.info("Audit logs unavailable or backend is offline.")
