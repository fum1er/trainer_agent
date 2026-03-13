"""
Auto-load user + profile from DB into session state.
Call at the top of any Streamlit page before checking session_state.user/profile.
"""
import streamlit as st


def init_session():
    """Populate session_state.user and session_state.profile from DB if missing."""
    from src.database.database import get_db
    from src.database.models import User, UserProfile

    # Multi-user: don't auto-load any user from DB — each user authenticates via Strava OAuth

    if "user" in st.session_state and (
        "profile" not in st.session_state or not st.session_state.profile.get("ftp")
    ):
        with get_db() as db:
            p = db.query(UserProfile).filter(
                UserProfile.user_id == st.session_state.user["id"]
            ).first()
            if p and p.ftp:
                st.session_state.profile = {
                    "ftp": p.ftp,
                    "weight": p.weight,
                    "ctl": p.ctl or 0,
                    "atl": p.atl or 0,
                    "tsb": p.tsb or 0,
                    "typical_workout_duration": 90,
                }
