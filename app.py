import os
import datetime
import requests
import streamlit as st
import firebase_admin
from firebase_admin import credentials, auth, db

# ================= CONFIG =================
DAILY_LIMIT = 20000

# Required environment variables (set these in your environment or Streamlit secrets)
FIREBASE_API_KEY = os.getenv("FIREBASE_API_KEY")  # Firebase Web API key (not service account)
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL")    # e.g. "https://your-project.firebaseio.com/"
GOOGLE_CREDS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")  # path to service account JSON (or set up another secret method)

if FIREBASE_API_KEY is None:
    raise RuntimeError("FIREBASE_API_KEY environment variable is required.")

if FIREBASE_DB_URL is None:
    raise RuntimeError("FIREBASE_DB_URL environment variable is required.")

# ================= FIREBASE ADMIN (server-side) =================
if not firebase_admin._apps:
    if GOOGLE_CREDS is None:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS env var (service account JSON path) is required for firebase_admin.")
    cred = credentials.Certificate(GOOGLE_CREDS)
    firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})

# ================= HELPERS: Firebase Auth REST =================
def firebase_sign_in(email: str, password: str):
    """Sign in with email & password via Firebase Auth REST API. Returns JSON on success."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(url, json=payload)
    if r.ok:
        return r.json()
    # propagate meaningful error
    try:
        err = r.json().get("error", {}).get("message", r.text)
    except Exception:
        err = r.text
    raise Exception(f"Sign-in failed: {err}")

def firebase_sign_up(email: str, password: str):
    """Create a new user via Firebase Auth REST API and return the response JSON."""
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    r = requests.post(url, json=payload)
    if r.ok:
        return r.json()
    try:
        err = r.json().get("error", {}).get("message", r.text)
    except Exception:
        err = r.text
    raise Exception(f"Sign-up failed: {err}")

# ================= USER DATA =================
def get_data(uid: str):
    ref = db.reference(f"users/{uid}")
    data = ref.get()

    if not data:
        data = {
            "xp": 0,
            "level": 1,
            "tokens": {"used": 0, "date": str(datetime.date.today())},
        }
        ref.set(data)

    # Defensive defaults if structure partial
    if "xp" not in data:
        data["xp"] = 0
    if "level" not in data:
        data["level"] = 1
    if "tokens" not in data or not isinstance(data["tokens"], dict):
        data["tokens"] = {"used": 0, "date": str(datetime.date.today())}
    if "date" not in data["tokens"]:
        data["tokens"]["date"] = str(datetime.date.today())
    if "used" not in data["tokens"]:
        data["tokens"]["used"] = 0

    return data

def update(uid: str, data: dict):
    db.reference(f"users/{uid}").update(data)

# ================= TOKEN USAGE =================
def use_tokens(uid: str, cost: int):
    data = get_data(uid)
    today = str(datetime.date.today())

    if data["tokens"].get("date") != today:
        data["tokens"] = {"used": 0, "date": today}

    if data["tokens"]["used"] + cost > DAILY_LIMIT:
        return False

    data["tokens"]["used"] += cost
    update(uid, {"tokens": data["tokens"]})
    return True

# ================= XP =================
def add_xp(uid: str, amount: int):
    data = get_data(uid)
    data["xp"] = data.get("xp", 0) + amount
    data["level"] = 1 + data["xp"] // 100
    update(uid, {"xp": data["xp"], "level": data["level"]})

# ================= AUTH UI =================
def login():
    st.title("🔐 Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login"):
            if not email or not password:
                st.error("Email and password are required.")
                return
            try:
                res = firebase_sign_in(email, password)
                # res contains idToken, localId (uid), etc.
                st.session_state.uid = res["localId"]
                st.session_state.idToken = res.get("idToken")
                st.session_state.user = email
                st.success("Login successful")
                st.experimental_rerun()
            except Exception as e:
                st.error(str(e))

    with col2:
        if st.button("Sign Up"):
            if not email or not password:
                st.error("Email and password are required to sign up.")
                return
            try:
                res = firebase_sign_up(email, password)
                st.session_state.uid = res["localId"]
                st.session_state.idToken = res.get("idToken")
                st.session_state.user = email
                st.success("Account created and logged in")
                st.experimental_rerun()
            except Exception as e:
                st.error(str(e))

# ================= CHAT =================
def chat():
    st.title("💬 Chat")
    msg = st.text_input("Ask")

    if st.button("Send"):
        if "uid" not in st.session_state:
            st.error("Not authenticated.")
            return

        if not use_tokens(st.session_state.uid, 10):
            st.error("Daily token limit reached")
            return

        # Placeholder for AI answer --- integrate your model/service here
        st.write("🤖 AI:", f"Answer for '{msg}'")
        add_xp(st.session_state.uid, 10)

# ================= DASHBOARD =================
def dashboard():
    data = get_data(st.session_state.uid)

    st.title("📊 Dashboard")
    st.metric("Level", data.get("level", 1))
    st.metric("XP", data.get("xp", 0))
    left = max(0, DAILY_LIMIT - data["tokens"].get("used", 0))
    st.metric("Tokens Left", left)

# ================= LOGOUT =================
def logout():
    for k in ("uid", "idToken", "user"):
        if k in st.session_state:
            del st.session_state[k]
    st.experimental_rerun()

# ================= MAIN =================
if "user" not in st.session_state:
    login()
else:
    st.sidebar.write(f"Signed in as: {st.session_state.user}")
    if st.sidebar.button("Logout"):
        logout()

    page = st.sidebar.radio("Menu", ["Chat", "Dashboard"])

    if page == "Chat":
        chat()
    else:
        dashboard()