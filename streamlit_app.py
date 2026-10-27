"""
Logic Commerce & Autonomous Order Management System.
A real, enterprise-grade e-commerce application with customer order tracking,
catalog browsing, automated policy guardrails, and compliance audit trail.
Connects with FastAPI backend:
- POST /login
- GET  /orders
- GET  /orders/{order_id}
- GET  /products
- POST /chat
- POST /confirm
- GET  /audit
- GET  /health
"""
import json
from datetime import datetime, timezone
import requests
import streamlit as st

API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Logic Commerce · Order & Support Hub",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
if "token" not in st.session_state:
    st.session_state.token = None
if "customer_email" not in st.session_state:
    st.session_state.customer_email = ""
if "customer_name" not in st.session_state:
    st.session_state.customer_name = ""
if "customer_id" not in st.session_state:
    st.session_state.customer_id = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "pending_change_request" not in st.session_state:
    st.session_state.pending_change_request = None
if "queued_prompt" not in st.session_state:
    st.session_state.queued_prompt = None
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "💬 Order Support Desk"

# ---------------------------------------------------------------------------
# High-Fidelity Enterprise Dark Theme CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    }
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Overall Dark Canvas */
    .stApp {
        background-color: #090a0f !important;
        color: #f1f5f9;
    }

    header[data-testid="stHeader"] {
        background: transparent !important;
    }

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #0f1117 !important;
        border-right: 1px solid #1e2230 !important;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
    }

    /* Brand Header */
    .brand-container {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 1.2rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid #1e2433;
    }
    .brand-icon {
        width: 40px;
        height: 40px;
        border-radius: 10px;
        background: linear-gradient(135deg, #2563eb 0%, #3b82f6 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
        color: #fff;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4);
    }
    .brand-title {
        font-size: 1.18rem;
        font-weight: 800;
        color: #ffffff;
        letter-spacing: -0.02em;
        line-height: 1.1;
    }
    .brand-subtitle {
        font-size: 0.72rem;
        color: #60a5fa;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }

    /* Customer Profile Card */
    .profile-card {
        background: #141722;
        border: 1px solid #222838;
        border-radius: 12px;
        padding: 0.9rem;
        margin-bottom: 1.2rem;
    }
    .profile-avatar {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: linear-gradient(135deg, #3b82f6, #1d4ed8);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        color: #fff;
        font-size: 0.85rem;
    }

    /* Order Card Container */
    .order-card {
        background: #11141e;
        border: 1px solid #1e2434;
        border-radius: 14px;
        padding: 1.3rem;
        margin-bottom: 1rem;
        transition: border-color 0.2s, box-shadow 0.2s;
    }
    .order-card:hover {
        border-color: #3b82f6;
        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
    }

    /* Status Badges */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 11px;
        border-radius: 999px;
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }
    .status-placed { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
    .status-shipped { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    .status-delivered { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .status-cancelled { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
    .status-failed { background: rgba(225, 29, 72, 0.15); color: #fb7185; border: 1px solid rgba(225, 29, 72, 0.3); }

    /* Shipment Tracking Tracker Bar */
    .timeline-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #161a26;
        border-radius: 10px;
        padding: 0.8rem 1.2rem;
        margin: 1rem 0;
        position: relative;
    }
    .timeline-step {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        font-size: 0.72rem;
        font-weight: 600;
        z-index: 1;
    }
    .timeline-dot {
        width: 14px;
        height: 14px;
        border-radius: 50%;
        margin-bottom: 6px;
    }
    .dot-done { background: #10b981; box-shadow: 0 0 10px rgba(16, 185, 129, 0.5); }
    .dot-current { background: #3b82f6; box-shadow: 0 0 10px rgba(59, 130, 246, 0.7); border: 2px solid #ffffff; }
    .dot-pending { background: #334155; }

    /* Product Catalog Card */
    .catalog-card {
        background: #121520;
        border: 1px solid #1e2333;
        border-radius: 14px;
        padding: 1.2rem;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        transition: transform 0.2s, border-color 0.2s;
    }
    .catalog-card:hover {
        transform: translateY(-3px);
        border-color: #3b82f6;
    }
    .catalog-icon {
        font-size: 2.2rem;
        margin-bottom: 0.6rem;
    }

    /* Change Confirmation Review Box */
    .review-box {
        background: #141724;
        border: 1px solid #f59e0b;
        border-radius: 14px;
        padding: 1.3rem;
        margin: 1rem 0;
        box-shadow: 0 6px 24px rgba(245, 158, 11, 0.15);
    }

    /* Action Chip */
    .quick-chip {
        display: inline-block;
        background: #151824;
        border: 1px solid #23293c;
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 0.78rem;
        color: #cbd5e1;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# API Client Helper
# ---------------------------------------------------------------------------
def api_request(method: str, path: str, json_data: dict = None):
    url = f"{API_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {st.session_state.token}"} if st.session_state.token else {}
    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, timeout=6)
        else:
            resp = requests.post(url, headers=headers,
                                 json=json_data, timeout=6)
        if resp.status_code == 401 and st.session_state.token and path != "/login":
            st.session_state.token = None
        return resp.status_code, resp.json()
    except Exception as e:
        return 500, {
            "error": f"Backend unavailable at {API_BASE_URL}. Ensure FastAPI is running.",
            "detail": str(e),
        }


# ============================================================================
# LOGIN GATE (rule R1): nothing else renders until the backend issues a token.
# The token comes from POST /login and is sent as a Bearer header by api_request.
# ============================================================================
if not st.session_state.token:
    # Hide the sidebar on the login screen and narrow the page
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"], div[data-testid="collapsedControl"] { display: none !important; }
        .login-wrap { text-align: center; margin-top: 6vh; margin-bottom: 1.4rem; }
        .login-title { font-size: 1.9rem; font-weight: 700; color: #f8fafc; letter-spacing: -0.03em; }
        .login-sub { font-size: 0.85rem; color: #94a3b8; margin-top: 0.3rem; }
        div[data-testid="stForm"] {
            background: #13161f; border: 1px solid #1f2433; border-radius: 14px; padding: 1.5rem;
        }
        </style>
        <div class="login-wrap">
            <div class="hero-logo-box">🤖</div>
            <div class="login-title">Welcome to Logic</div>
            <div class="login-sub">Sign in to manage your orders with the AI support agent</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, col_login, _ = st.columns([1, 1.2, 1])
    with col_login:
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="you@example.com")
            pin = st.text_input("PIN", type="password",
                                placeholder="4 to 8 digits")
            submitted = st.form_submit_button(
                "Sign in", type="primary", use_container_width=True)
        st.caption("Demo account: alice@example.com / PIN 1234")

        if submitted:
            # Validate before calling the backend so the user gets a clear message
            if not email.strip() or not pin:
                st.error("Please enter both your email and PIN.")
            elif not (pin.isdigit() and 4 <= len(pin) <= 8):
                st.error("PIN must be 4 to 8 digits.")
            else:
                code, resp = api_request(
                    "POST", "/login", {"email": email.strip(), "pin": pin})
                if code == 200:
                    # Authenticated: store identity + token, then rerun into the main app
                    st.session_state.token = resp["access_token"]
                    st.session_state.customer_email = resp["customer_email"]
                    st.session_state.customer_name = resp["customer_name"]
                    st.rerun()
                elif "error" in resp:  # backend unreachable
                    st.error(resp["error"])
                # 401 wrong credentials / 429 locked out
                elif isinstance(resp.get("detail"), str):
                    st.error(resp["detail"])
                else:  # 422 format errors
                    st.error(
                        "Enter a valid email and a numeric PIN of 4 to 8 digits.")
    st.stop()  # never render the app below without a token


# ============================================================================
# SIDEBAR: Navigation, History Timeline, Customer Card, Logout
# ============================================================================
with st.sidebar:
    st.markdown(
        """
        <div class="brand-container">
            <div class="brand-icon">🛍️</div>
            <div>
                <div class="brand-title">LOGIC COMMERCE</div>
                <div class="brand-subtitle">Order & Support Desk</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Customer Profile Card
    initials = "".join(
        [part[0] for part in st.session_state.customer_name.split()[:2]]).upper() or "CU"
    st.markdown(
        f"""
        <div class="profile-card">
            <div style="display:flex; align-items:center; gap:12px;">
                <div class="profile-avatar">{initials}</div>
                <div>
                    <div style="font-weight:700; font-size:0.92rem; color:#f8fafc;">{st.session_state.customer_name}</div>
                    <div style="font-size:0.75rem; color:#94a3b8;">{st.session_state.customer_email}</div>
                </div>
            </div>
            <div style="margin-top:0.7rem; font-size:0.73rem; color:#64748b; display:flex; justify-content:space-between;">
                <span>Tenant: <b>Customer #{st.session_state.customer_id}</b></span>
                <span style="color:#10b981; font-weight:600;">● Verified</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Quick Switch Customer (Demonstrates strict multi-tenant isolation)
    with st.expander("🔄 Switch Customer Account (RBAC Demo)", expanded=False):
        st.caption(
            "Demonstrate multi-tenant data isolation. Alice and Bob cannot access or modify each other's orders.")
        if st.session_state.customer_email == "alice@example.com":
            if st.button("Switch to Bob Kumar (Ahmedabad)", use_container_width=True):
                code, resp = api_request(
                    "POST", "/login", {"email": "bob@example.com", "pin": "1234"})
                if code == 200:
                    st.session_state.token = resp["access_token"]
                    st.session_state.customer_email = resp["customer_email"]
                    st.session_state.customer_name = resp["customer_name"]
                    st.session_state.customer_id = resp["customer_id"]
                    st.session_state.chat_history = []
                    st.session_state.pending_change_request = None
                    st.rerun()
        else:
            if st.button("Switch to Alice Smith (Pune)", use_container_width=True):
                code, resp = api_request(
                    "POST", "/login", {"email": "alice@example.com", "pin": "1234"})
                if code == 200:
                    st.session_state.token = resp["access_token"]
                    st.session_state.customer_email = resp["customer_email"]
                    st.session_state.customer_name = resp["customer_name"]
                    st.session_state.customer_id = resp["customer_id"]
                    st.session_state.chat_history = []
                    st.session_state.pending_change_request = None
                    st.rerun()

    # Views Navigation
    st.markdown("<p style='font-size:0.7rem; font-weight:700; color:#64748b; letter-spacing:0.08em; text-transform:uppercase; margin-top:1.2rem; margin-bottom:0.5rem;'>PORTAL NAVIGATION</p>", unsafe_allow_html=True)
    page = st.radio(
        "Navigation",
        ["💬 Order Support Desk", "📦 My Orders & Tracking", "🛍️ Store Catalog"],
        label_visibility="collapsed",
    )

    st.markdown("---")

    # Backend Status
    code, health = api_request("GET", "/health")
    backend_up = (code == 200)
    st.markdown(
        f"""
        <div style="background:#13151f; border:1px solid #1f2331; border-radius:10px; padding:0.7rem; font-size:0.75rem;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="color:#94a3b8;">FastAPI Gateway:</span>
                <span style="color:{'#34d399' if backend_up else '#f87171'}; font-weight:700;">
                    {'● 127.0.0.1:8000 Online' if backend_up else '○ Offline'}
                </span>
            </div>
            <div style="color:#64748b; font-size:0.68rem; margin-top:4px;">
                Environment: development · v1.0.0
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Session Profile Card in Sidebar
    initials = "".join(w[0] for w in st.session_state.customer_name.split()[:2]).upper() or "?"
    st.markdown(
        f"""
        <div style="background:#151822; border:1px solid #232838; border-radius:10px; padding:0.75rem; margin-bottom:0.7rem;">
            <div style="display:flex; align-items:center; gap:10px;">
                <div style="width:32px; height:32px; border-radius:50%; background:#2563eb; display:flex; align-items:center; justify-content:center; font-weight:700; color:#fff;">{initials}</div>
                <div>
                    <div style="font-size:0.82rem; font-weight:600; color:#f8fafc;">{st.session_state.customer_name}</div>
                    <div style="font-size:0.7rem; color:#94a3b8;">{st.session_state.customer_email}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("🚪 Log out", use_container_width=True):
        st.session_state.token = None
        st.session_state.customer_email = ""
        st.session_state.customer_name = ""
        st.session_state.customer_id = None
        st.session_state.chat_history = []
        st.session_state.pending_change_request = None
        st.session_state.queued_prompt = None
        st.rerun()


# ============================================================================
# PAGE 1: 💬 Order Support Desk (Autonomous Conversational Agent)
# ============================================================================
if page == "💬 Order Support Desk":
    st.markdown(
        """
        <div style="margin-bottom:1.5rem;">
            <h1 style="font-size:1.8rem; font-weight:800; color:#ffffff; margin:0 0 0.3rem 0;">Customer Order Support Desk</h1>
            <p style="color:#94a3b8; font-size:0.88rem; margin:0;">
                Chat naturally to update delivery addresses, cancel orders, or track shipments. Governed by deterministic business rules and safety guardrails.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Quick Inquiries Bar
    st.markdown("<p style='font-size:0.75rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'>Quick Customer Inquiries:</p>", unsafe_allow_html=True)
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        if st.button("📍 Change Address (#10001)", use_container_width=True):
            st.session_state.queued_prompt = "Change shipping address for order 10001 to 12 MG Road, Pune"
            st.rerun()
    with q2:
        if st.button("🚚 Track Shipment (#10002)", use_container_width=True):
            st.session_state.queued_prompt = "Track order 10002"
            st.rerun()
    with q3:
        if st.button("❌ Cancel Order (#10001)", use_container_width=True):
            st.session_state.queued_prompt = "Cancel order 10001"
            st.rerun()
    with q4:
        if st.button("🛡️ Test Shipped Block (#10002)", use_container_width=True):
            st.session_state.queued_prompt = "Change shipping address for order 10002 to 55 Lake Road"
            st.rerun()

    st.markdown("---")

    # Render Chat Stream
    if not st.session_state.chat_history:
        st.info("👋 Welcome! You can ask questions about your orders, request an address update before courier dispatch, or track delivery status.")

    for msg in st.session_state.chat_history:
        role = msg.get("role", "assistant")
        avatar = "👤" if role == "user" else "🛍️"
        with st.chat_message(role, avatar=avatar):
            st.markdown(msg.get("content", ""))
            trace = msg.get("trace")
            if trace:
                with st.expander("🔍 Guardrail Decision & Latency Trace", expanded=False):
                    for step in trace:
                        node = step.get("node", "Checkpoint")
                        stat = step.get("status", "OK")
                        color = "#34d399" if any(w in stat.lower() for w in [
                                                 "success", "ok", "customer", "intent"]) else "#fbbf24"
                        st.markdown(
                            f"- **{node}**: <span style='color:{color}; font-weight:600;'>{stat}</span>", unsafe_allow_html=True)

    # Render Pending State Modification Confirmation Review Box
    if st.session_state.pending_change_request:
        cr = st.session_state.pending_change_request
        order_target = cr.get("order_id")
        intent_val = cr.get("intent")
        curr_state = cr.get("preview", {}).get("current")
        new_state = cr.get("preview", {}).get("new")

        st.markdown(
            f"""
            <div class="review-box">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.7rem;">
                    <span style="font-size:1rem; font-weight:800; color:#fbbf24;">
                        ⚠️ Confirmation Required: Proposed Order Modification
                    </span>
                    <span style="font-size:0.75rem; background:#1e293b; color:#94a3b8; padding:3px 10px; border-radius:999px;">
                        Valid for 5 minutes
                    </span>
                </div>
                <div style="font-size:0.85rem; color:#cbd5e1; margin-bottom:0.9rem;">
                    The agent verified that <b>Order #{order_target}</b> is eligible for modification. Review the state change before writing to the database:
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        d_col1, d_col2 = st.columns(2)
        with d_col1:
            st.markdown("**Current State in Database:**")
            st.code(json.dumps(
                {"order_id": order_target, "state": curr_state}, indent=2), language="json")
        with d_col2:
            st.markdown("**Proposed State to Commit:**")
            st.code(json.dumps(
                {"order_id": order_target, "state": new_state}, indent=2), language="json")

        c_confirm, c_decline = st.columns(2)
        with c_confirm:
            if st.button("✅ Confirm & Apply Changes", type="primary", use_container_width=True):
                s_code, resp = api_request("POST", "/confirm", {
                    "request_id": cr["request_id"],
                    "action": "confirm",
                    "idempotency_key": cr["idempotency_key"]
                })
                if s_code == 200:
                    msg = resp.get(
                        "message", "Order successfully updated in database.")
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": f"✅ **Confirmed & Applied:** {msg}"})
                    st.toast(
                        "Database updated and audit trail recorded!", icon="✅")
                else:
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": f"❌ **Error:** {resp.get('detail')}"})
                st.session_state.pending_change_request = None
                st.rerun()

        with c_decline:
            if st.button("✕ Decline & Discard", use_container_width=True):
                api_request("POST", "/confirm", {
                    "request_id": cr["request_id"],
                    "action": "cancel",
                    "idempotency_key": cr["idempotency_key"]
                })
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": "❌ Change request declined and discarded."})
                st.session_state.pending_change_request = None
                st.rerun()

    # Chat Input Box
    user_msg = st.chat_input(
        "Ask a question or enter an order instruction...") or st.session_state.queued_prompt
    st.session_state.queued_prompt = None

    if user_msg:
        st.session_state.chat_history.append(
            {"role": "user", "content": user_msg})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_msg)

        with st.chat_message("assistant", avatar="🛍️"):
            with st.spinner("Processing request and verifying security guardrails..."):
                status_code, resp = api_request(
                    "POST", "/chat", {"message": user_msg})

            if status_code == 200:
                reply = resp.get("reply", "")
                st.markdown(reply)

                if resp.get("needs_confirmation") and resp.get("change_request"):
                    st.session_state.pending_change_request = resp["change_request"]

                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": reply,
                    "trace": resp.get("trace", [])
                })
                st.rerun()
            else:
                err = resp.get(
                    "detail", "Error communicating with backend.")
                st.error(err)
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": f"⚠️ {err}"})


# ============================================================================
# PAGE 2: 📦 My Orders & Tracking (Real E-Commerce Order Management)
# ============================================================================
elif page == "📦 My Orders & Tracking":
    col_hdr, col_btn = st.columns([5, 1])
    with col_hdr:
        st.markdown(
            """
            <div style="margin-bottom:1.5rem;">
                <h1 style="font-size:1.8rem; font-weight:800; color:#ffffff; margin:0 0 0.3rem 0;">My Orders & Tracking</h1>
                <p style="color:#94a3b8; font-size:0.88rem; margin:0;">View active and past shipments, line items, and delivery status.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_btn:
        if st.button("🔄 Refresh Orders", use_container_width=True):
            st.rerun()

    status_code, orders = api_request("GET", "/orders")

    if status_code != 200 or not isinstance(orders, list):
        st.error("Failed to load orders from backend. Make sure FastAPI is running on port 8000.")
    elif len(orders) == 0:
        st.info("No orders found for your account.")
    else:
        for o in orders:
            order_id = o.get("order_id")
            order_ref = o.get("order_ref", f"ORD-{order_id}")
            status_val = o.get("status", "placed").lower()
            pay_status = o.get("payment_status", "Success")
            pay_method = o.get("payment_method", "Credit Card")
            total = o.get("total_amount", "0.00")
            ship_addr = o.get("shipping_address", "N/A")
            delivery_date = o.get("delivery_date", "TBD")
            items = o.get("items", [])
            version = o.get("version", 1)

            # Determine visual badge class
            if status_val == "placed":
                badge_html = '<span class="status-badge status-placed">● Placed & Verified</span>'
                step_idx = 1
            elif status_val == "shipped":
                badge_html = '<span class="status-badge status-shipped">🚚 In Transit (Dispatched)</span>'
                step_idx = 2
            elif status_val == "delivered":
                badge_html = '<span class="status-badge status-delivered">✅ Delivered</span>'
                step_idx = 3
            elif status_val == "cancelled":
                badge_html = '<span class="status-badge status-cancelled">❌ Cancelled & Refunded</span>'
                step_idx = 0
            else:
                badge_html = f'<span class="status-badge status-placed">{status_val.upper()}</span>'
                step_idx = 1

            if pay_status == "Failed":
                badge_html += ' <span class="status-badge status-failed">⚠️ Payment Failed</span>'

            # Order Card
            with st.container(border=True):
                # Header row
                c_title, c_meta = st.columns([3, 2])
                with c_title:
                    st.markdown(
                        f"""
                        <div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">
                            <span style="font-size:1.25rem; font-weight:800; color:#ffffff;">Order #{order_ref}</span>
                            {badge_html}
                        </div>
                        <div style="font-size:0.78rem; color:#64748b;">
                            Booking Ref: <code>{o.get('booking_id', 'N/A')}</code> · DB Version: <b>v{version}</b> · Payment: <b>{pay_method} ({pay_status})</b>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with c_meta:
                    st.markdown(
                        f"""
                        <div style="text-align:right;">
                            <div style="font-size:1.35rem; font-weight:800; color:#34d399;">₹{float(total):,.2f}</div>
                            <div style="font-size:0.75rem; color:#94a3b8;">Est. Delivery: <b>{delivery_date}</b></div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # Visual Delivery Tracker Timeline (if not cancelled)
                if status_val != "cancelled":
                    st.markdown(
                        f"""
                        <div class="timeline-bar">
                            <div class="timeline-step">
                                <div class="timeline-dot dot-done"></div>
                                <span style="color:#10b981;">1. Placed</span>
                            </div>
                            <div style="flex:1; height:2px; background:{'#10b981' if step_idx >= 1 else '#334155'}; margin:0 8px -18px;"></div>
                            <div class="timeline-step">
                                <div class="timeline-dot {'dot-done' if step_idx >= 2 else ('dot-current' if step_idx == 1 else 'dot-pending')}"></div>
                                <span style="color:{'#10b981' if step_idx >= 2 else ('#60a5fa' if step_idx == 1 else '#64748b')};">2. Confirmed</span>
                            </div>
                            <div style="flex:1; height:2px; background:{'#10b981' if step_idx >= 2 else '#334155'}; margin:0 8px -18px;"></div>
                            <div class="timeline-step">
                                <div class="timeline-dot {'dot-done' if step_idx >= 3 else ('dot-current' if step_idx == 2 else 'dot-pending')}"></div>
                                <span style="color:{'#10b981' if step_idx >= 3 else ('#60a5fa' if step_idx == 2 else '#64748b')};">3. In Transit</span>
                            </div>
                            <div style="flex:1; height:2px; background:{'#10b981' if step_idx >= 3 else '#334155'}; margin:0 8px -18px;"></div>
                            <div class="timeline-step">
                                <div class="timeline-dot {'dot-done' if step_idx >= 3 else 'dot-pending'}"></div>
                                <span style="color:{'#10b981' if step_idx >= 3 else '#64748b'};">4. Delivered</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # Items and Shipping details
                col_items, col_shipping = st.columns([3, 2])
                with col_items:
                    st.markdown("<p style='font-size:0.8rem; font-weight:700; color:#94a3b8; margin:0.4rem 0;'>Package Line Items:</p>", unsafe_allow_html=True)
                    for it in items:
                        prod = it.get("product") or {}
                        qty = it.get("quantity", 1)
                        price = it.get("item_price", "0.00")
                        st.markdown(
                            f"""
                            <div style="display:flex; justify-content:space-between; align-items:center; background:#161925; border:1px solid #202638; border-radius:8px; padding:0.55rem 0.8rem; margin-bottom:0.35rem; font-size:0.82rem;">
                                <div>
                                    <span style="font-weight:600; color:#f1f5f9;">{prod.get('name', 'Product Item')}</span>
                                    <span style="color:#64748b; font-size:0.75rem; margin-left:6px;">({prod.get('base_colour', '')} · {prod.get('article_type', '')})</span>
                                </div>
                                <div style="font-weight:700; color:#e2e8f0;">
                                    {qty} × ₹{float(price):,.2f}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                with col_shipping:
                    st.markdown("<p style='font-size:0.8rem; font-weight:700; color:#94a3b8; margin:0.4rem 0;'>Destination Shipping Address:</p>", unsafe_allow_html=True)
                    st.markdown(
                        f"""
                        <div style="background:#161925; border:1px solid #202638; border-radius:8px; padding:0.65rem 0.8rem; font-size:0.82rem;">
                            <div style="color:#f1f5f9; font-weight:500;">📍 {ship_addr}</div>
                            <div style="font-size:0.72rem; color:#64748b; margin-top:4px;">
                                Carrier: <b>{'BlueDart Express #BD-88239102' if status_val == 'shipped' else 'Delhivery Surface'}</b>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # Quick action buttons
                st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
                b1, b2, b3, _ = st.columns([1.5, 1.5, 1.5, 3])
                with b1:
                    if status_val == "placed" and pay_status != "Failed":
                        if st.button("📍 Change Address", key=f"btn_addr_{order_id}", use_container_width=True):
                            st.session_state.queued_prompt = f"Change shipping address for order {order_id} to 12 MG Road, Pune"
                            st.toast("Address change loaded in Support Desk! Switch to 'Order Support Desk' to confirm.", icon="📍")
                    else:
                        st.button("📍 Change Address", key=f"btn_addr_dis_{order_id}", disabled=True, help="Address modification locked (Only allowed for placed, paid orders)")

                with b2:
                    if status_val == "placed":
                        if st.button("❌ Cancel Order", key=f"btn_canc_{order_id}", use_container_width=True):
                            st.session_state.queued_prompt = f"Cancel order {order_id}"
                            st.toast("Cancellation loaded in Support Desk!", icon="❌")
                    else:
                        st.button("❌ Cancel Order", key=f"btn_canc_dis_{order_id}", disabled=True, help="Cancellation locked (Only allowed for placed orders)")

                with b3:
                    if st.button("💬 Support Inquire", key=f"btn_supp_{order_id}", use_container_width=True):
                        st.session_state.queued_prompt = f"Track order {order_id}"
                        st.toast("Loaded tracking inquiry into Support Desk!", icon="💬")



# ============================================================================
# PAGE 3: 🛍️ Store Catalog (Real Products & Realistic E-Commerce Inventory)
# ============================================================================
elif page == "🛍️ Store Catalog":
    st.markdown(
        """
        <div style="margin-bottom:1.5rem;">
            <h1 style="font-size:1.8rem; font-weight:800; color:#ffffff; margin:0 0 0.3rem 0;">Product Store Catalog</h1>
            <p style="color:#94a3b8; font-size:0.88rem; margin:0;">Explore verified items in the Logic Commerce warehouse inventory with real specs and pricing.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    code, products = api_request("GET", "/products")

    if code != 200 or not isinstance(products, list):
        st.error("Failed to load catalog from backend.")
    else:
        cols = st.columns(3)
        product_icons = {
            101: "🎧",
            102: "⌨️",
            103: "👟",
            104: "👛",
            105: "👕",
            106: "🔋",
        }
        product_prices = {
            101: 24990.00,
            102: 8499.00,
            103: 9995.00,
            104: 3495.00,
            105: 1299.00,
            106: 11999.00,
        }

        for idx, p in enumerate(products):
            p_id = p.get("product_id")
            icon = product_icons.get(p_id, "📦")
            price = product_prices.get(p_id, 2999.00)
            with cols[idx % 3]:
                st.markdown(
                    f"""
                    <div class="catalog-card">
                        <div>
                            <div class="catalog-icon">{icon}</div>
                            <span style="font-size:0.7rem; font-weight:700; color:#60a5fa; text-transform:uppercase; letter-spacing:0.05em;">{p.get('category')} · {p.get('sub_category')}</span>
                            <h3 style="font-size:1.05rem; font-weight:700; color:#ffffff; margin:0.3rem 0 0.4rem 0;">{p.get('name')}</h3>
                            <p style="font-size:0.76rem; color:#94a3b8; margin:0 0 0.8rem 0;">
                                Color: <b>{p.get('base_colour')}</b> · Article: <b>{p.get('article_type')}</b>
                            </p>
                        </div>
                        <div>
                            <div style="display:flex; justify-content:space-between; align-items:baseline; margin-bottom:0.7rem;">
                                <span style="font-size:1.25rem; font-weight:800; color:#34d399;">₹{price:,.2f}</span>
                                <span style="font-size:0.72rem; color:#10b981; font-weight:600;">● In Stock (Ships Today)</span>
                            </div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(f"🛒 Order Item #{p_id}", key=f"cat_order_{p_id}", use_container_width=True):
                    code, new_order = api_request("POST", "/orders", {"product_id": p_id, "quantity": 1})
                    if code in (200, 201):
                        st.toast(f"🎉 Order #{new_order.get('order_ref')} placed successfully! Track it in the Support Desk.", icon="🛍️")
                        st.session_state.queued_prompt = f"Track order {new_order.get('order_id')}"
                        st.rerun()
                    else:
                        st.error(f"Failed to place order: {new_order.get('detail', 'Unknown error')}")
