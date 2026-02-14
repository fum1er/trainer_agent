"""
Analytics page - Strava connection and activity sync
"""
import streamlit as st
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.strava.auth import StravaAuth
from src.strava.client import StravaDataClient
from src.strava.data_processor import StravaDataProcessor
from src.database.database import get_db
from src.database.models import User, Activity, UserProfile
from datetime import datetime

st.title("📊 Analytics & Strava Sync")

# Strava OAuth section
st.subheader("Strava Connection")

if "user" not in st.session_state or not st.session_state.get("strava_connected"):
    st.info("Connect your Strava account to sync your training data")

    auth = StravaAuth()

    # OAuth flow
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("Connect Strava", type="primary", use_container_width=True):
            st.session_state.show_auth_url = True

    if st.session_state.get("show_auth_url"):
        auth_url = auth.get_authorization_url()

        st.success("✅ Step 1: Copy this URL and paste it in a NEW browser tab")
        st.code(auth_url, language="text")

        st.info("💡 TIP: Right-click the code above, select all, and copy. Then paste in a new tab.")

        st.warning(
            "⚠️ Step 2: After authorizing on Strava, you'll see 'Page not found'. That's NORMAL!\n\n"
            "Look at the URL bar - it contains your code:\n\n"
            "`http://localhost:8501/...?code=XXXXXXXXXX&scope=...`\n\n"
            "Copy ONLY the code (everything between `code=` and `&scope`)"
        )

    # Code input
    st.divider()
    code = st.text_input("Step 3: Paste the authorization code here:", placeholder="Paste code from URL...")

    if code:
        with st.spinner("Connecting to Strava..."):
            try:
                tokens = auth.exchange_code_for_token(code)

                # Create or update user in database
                with get_db() as db:
                    # For Phase 1: simple user creation
                    user = User(
                        name="Strava User",
                        strava_access_token=tokens["access_token"],
                        strava_refresh_token=tokens["refresh_token"],
                        strava_token_expires_at=tokens["expires_at"],
                    )
                    db.add(user)
                    db.commit()

                    st.session_state.user = {"id": user.id, "name": user.name}
                    st.session_state.strava_connected = True
                    st.success("Strava connected successfully!")
                    st.rerun()
            except Exception as e:
                st.error(f"Error connecting to Strava: {e}")
else:
    st.success("Strava connected!")

    # Sync section
    st.subheader("Sync Training Data")

    if st.button("Sync Last 6 Months"):
        with st.spinner("Fetching activities from Strava..."):
            try:
                # Get user from database
                with get_db() as db:
                    user = (
                        db.query(User).filter(User.id == st.session_state.user["id"]).first()
                    )
                    profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()

                    if not profile:
                        st.warning("Please set your FTP in Settings first!")
                        st.stop()

                    # Fetch activities
                    client = StravaDataClient(user.strava_access_token)
                    activities = client.get_activities()

                    st.info(f"Found {len(activities)} activities. Processing...")

                    # Process activities
                    processor = StravaDataProcessor(ftp=profile.ftp)
                    processed = processor.process_activities_batch(activities)

                    # Store in database
                    for activity_data in processed:
                        activity = Activity(
                            user_id=user.id,
                            strava_activity_id=activity_data["id"],
                            name=activity_data["name"],
                            activity_type=activity_data["type"],
                            start_date=activity_data["start_date"],
                            duration=activity_data["moving_time"],
                            distance=activity_data["distance"],
                            average_watts=activity_data.get("average_watts"),
                            normalized_power=activity_data.get("normalized_power"),
                            tss=activity_data.get("tss"),
                            intensity_factor=activity_data.get("intensity_factor"),
                        )
                        db.merge(activity)  # Upsert

                    db.commit()

                    # Calculate CTL/ATL/TSB
                    from src.strava.metrics import TrainingMetrics

                    activities_list = [
                        {"start_date": a.start_date, "tss": a.tss}
                        for a in db.query(Activity)
                        .filter(Activity.user_id == user.id)
                        .all()
                    ]
                    metrics = TrainingMetrics.calculate_ctl_atl_tsb(activities_list)

                    profile.ctl = metrics["ctl"]
                    profile.atl = metrics["atl"]
                    profile.tsb = metrics["tsb"]
                    db.commit()

                    st.success(f"Synced {len(processed)} activities!")
                    st.metric("CTL", metrics["ctl"])
                    st.metric("ATL", metrics["atl"])
                    st.metric("TSB", metrics["tsb"])

            except Exception as e:
                st.error(f"Error syncing activities: {e}")
                import traceback

                st.code(traceback.format_exc())

    # Display synced activities
    st.subheader("Recent Activities")
    with get_db() as db:
        activities = (
            db.query(Activity)
            .filter(Activity.user_id == st.session_state.user["id"])
            .order_by(Activity.start_date.desc())
            .limit(20)
            .all()
        )

        if activities:
            data = [
                {
                    "Date": a.start_date.strftime("%Y-%m-%d"),
                    "Name": a.name,
                    "Type": a.activity_type,
                    "Duration": f"{a.duration // 60}min",
                    "TSS": round(a.tss, 1) if a.tss else "N/A",
                    "NP": round(a.normalized_power, 0) if a.normalized_power else "N/A",
                }
                for a in activities
            ]

            st.dataframe(data, use_container_width=True)
        else:
            st.info("No activities synced yet. Click 'Sync Last 6 Months' above.")
