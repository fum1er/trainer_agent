"""
Settings page - User profile and preferences management
"""
import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.database.database import get_db
from src.database.models import User, UserProfile, UserPreference

st.title("⚙️ Settings")

# Check if user exists
if "user" not in st.session_state:
    st.warning("Please connect Strava from the Analytics page first.")
    st.stop()

# Get user data
user_id = st.session_state.user["id"]

# Extract values from DB within session context
with get_db() as db:
    user = db.query(User).filter(User.id == user_id).first()
    profile_db = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    preferences_db = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()

    # Extract values to use outside session
    profile_ftp = profile_db.ftp if profile_db else 265
    profile_weight = profile_db.weight if profile_db and profile_db.weight else 70
    pref_duration = preferences_db.typical_workout_duration if preferences_db and preferences_db.typical_workout_duration else 90
    pref_recovery = preferences_db.recovery_preference if preferences_db and preferences_db.recovery_preference else "Moderate"
    pref_notes = preferences_db.notes if preferences_db and preferences_db.notes else ""

# User Profile Section
st.subheader("User Profile")

col1, col2 = st.columns(2)

with col1:
    ftp = st.number_input(
        "FTP (Watts)", value=int(profile_ftp), min_value=100, max_value=500, step=1
    )
    weight = st.number_input(
        "Weight (kg)",
        value=float(profile_weight),
        min_value=40.0,
        max_value=150.0, step=0.5
    )

with col2:
    st.markdown("**Calculated Power Zones**")
    if ftp:
        st.text(f"Z1 (Recovery): <{ftp * 0.55:.0f}W")
        st.text(f"Z2 (Endurance): {ftp * 0.56:.0f}-{ftp * 0.75:.0f}W")
        st.text(f"Z3 (Tempo): {ftp * 0.76:.0f}-{ftp * 0.90:.0f}W")
        st.text(f"Z4 (Threshold): {ftp * 0.91:.0f}-{ftp * 1.05:.0f}W")
        st.text(f"Z5 (VO2max): {ftp * 1.06:.0f}-{ftp * 1.20:.0f}W")

# Training Preferences
st.subheader("Training Preferences")

typical_duration = st.slider(
    "Typical workout duration (minutes)",
    min_value=30,
    max_value=180,
    value=pref_duration,
    step=15,
)

recovery_pref = st.select_slider(
    "Recovery preference",
    options=["Easy", "Moderate", "Hard"],
    value=pref_recovery,
)

# Agent Memory
st.subheader("Agent Memory")
notes = st.text_area(
    "Training notes for the AI coach",
    value=pref_notes,
    placeholder="e.g., I prefer longer intervals, don't like short VO2max reps",
    height=100,
)

# Save button
if st.button("Save Settings", type="primary"):
    with get_db() as db:
        # Update or create profile
        existing_profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
        if not existing_profile:
            existing_profile = UserProfile(user_id=user_id)
            db.add(existing_profile)

        profile = existing_profile

        profile.ftp = ftp
        profile.weight = weight

        # Calculate zones
        profile.zone1_max = ftp * 0.55
        profile.zone2_max = ftp * 0.75
        profile.zone3_max = ftp * 0.90
        profile.zone4_max = ftp * 1.05
        profile.zone5_max = ftp * 1.20
        profile.zone6_max = ftp * 1.50

        # Update or create preferences
        existing_prefs = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        if not existing_prefs:
            existing_prefs = UserPreference(user_id=user_id)
            db.add(existing_prefs)

        preferences = existing_prefs

        preferences.typical_workout_duration = typical_duration
        preferences.recovery_preference = recovery_pref
        preferences.notes = notes

        db.commit()

        st.success("Settings saved successfully!")

# Test Knowledge Base
st.markdown("---")
st.subheader("Test Knowledge Base")

query = st.text_input("Ask a training question:")
if query:
    with st.spinner("Searching knowledge base..."):
        try:
            from src.rag.knowledge_base import KnowledgeBase

            kb = KnowledgeBase()
            results = kb.query(query, limit=3)

            st.success(f"Found {len(results)} relevant passages:")
            for i, result in enumerate(results):
                with st.expander(f"Result {i+1} - Score: {result['score']:.3f}"):
                    st.markdown(f"**Source:** {result['metadata'].get('source', 'Unknown')}")
                    st.markdown(result["text"])
        except Exception as e:
            st.error(f"Error querying knowledge base: {e}")
            st.info(
                "Make sure you have run `python scripts/ingest_books.py` to populate the knowledge base."
            )
