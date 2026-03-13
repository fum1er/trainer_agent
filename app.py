"""
Trainer Agent - Main Streamlit Application
"""
import streamlit as st

# Page configuration
st.set_page_config(
    page_title="Trainer Agent",
    page_icon="🚴",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Auto-load user from database if not in session
import os
from src.database.database import get_db
from src.database.models import User, UserProfile
from src.database.auto_migrate import auto_migrate

# Run auto-migrations on startup (safe to run multiple times)
if "migrations_run" not in st.session_state:
    try:
        migrations = auto_migrate()
        if migrations:
            print(f"✓ Applied {len(migrations)} migrations: {migrations}")
        st.session_state.migrations_run = True
    except Exception as e:
        print(f"Warning: Auto-migration failed: {e}")

# Check if Strava was just connected via OAuth
if os.path.exists("data/.strava_connected") and "user" not in st.session_state:
    with open("data/.strava_connected", "r") as f:
        user_id = int(f.read().strip())
    with get_db() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            st.session_state.user = {"id": user.id, "name": user.name}
            st.session_state.strava_connected = True
    os.remove("data/.strava_connected")

# Multi-user: don't auto-load any user — each user must connect via Strava OAuth

# Load user profile if connected
if "user" in st.session_state and "profile" not in st.session_state:
    with get_db() as db:
        profile = db.query(UserProfile).filter(UserProfile.user_id == st.session_state.user["id"]).first()
        if profile:
            st.session_state.profile = {
                "ftp": profile.ftp,
                "ctl": profile.ctl,
                "atl": profile.atl,
                "tsb": profile.tsb,
            }

# Sidebar
with st.sidebar:
    st.title("🚴 Trainer Agent")
    st.markdown("---")
    st.markdown("Your AI cycling coach, powered by science")

    # User info (if logged in)
    if "user" in st.session_state:
        st.success(f"Welcome, {st.session_state.user['name']}!")
    else:
        st.warning("⚠️ Not connected to Strava")

# Home page content
st.title("Welcome to Trainer Agent")

# Strava connection section
st.markdown("---")

if "user" not in st.session_state or not st.session_state.get("strava_connected"):
    st.subheader("🔗 Get Started")
    st.info("Connect your Strava account to sync your training data and get personalized workouts.")
    from src.strava.auth import StravaAuth
    auth_url = StravaAuth().get_authorization_url()
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown(
            f'<a href="{auth_url}" target="_self">'
            '<button style="'
            'background-color: #FC4C02; '
            'color: white; '
            'padding: 15px 32px; '
            'font-size: 20px; '
            'border: none; '
            'border-radius: 8px; '
            'cursor: pointer; '
            'width: 100%;'
            '">🚴 Connect Strava</button>'
            '</a>',
            unsafe_allow_html=True
        )
else:
    st.success(f"✅ Connected as {st.session_state.user.get('name', 'Cyclist')}")
    st.info("Go to **Dashboard** in the sidebar to sync your activities.")


# Quick stats (if user logged in)
if "user" in st.session_state and "profile" in st.session_state:
    st.markdown("---")
    st.subheader("Quick Stats")

    col1, col2, col3, col4 = st.columns(4)
    profile = st.session_state.profile

    col1.metric("FTP", f"{profile.get('ftp', 0):.0f}W")
    col2.metric("CTL", f"{profile.get('ctl', 0):.1f}")
    col3.metric("ATL", f"{profile.get('atl', 0):.1f}")
    col4.metric("TSB", f"{profile.get('tsb', 0):.1f}")
