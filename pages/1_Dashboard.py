"""
Dashboard page - Overview of training metrics and recent activities
"""
import streamlit as st
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.database import get_db
from src.database.models import Activity, UserProfile
from src.visualization.charts import create_pmc_chart, create_weekly_tss_chart, create_zone_distribution_chart
from datetime import datetime, timedelta

st.title("Dashboard")

# Check if user is logged in
if "user" not in st.session_state:
    st.warning("Please connect your Strava account from the Analytics page first.")
    st.stop()

# Get user profile and activities
with get_db() as db:
    profile_db = db.query(UserProfile).filter(UserProfile.user_id == st.session_state.user["id"]).first()

    if not profile_db:
        st.warning("Please set your FTP in Settings and sync activities from Analytics.")
        st.stop()

    # Extract profile values within session
    profile_ftp = profile_db.ftp
    profile_ctl = profile_db.ctl
    profile_atl = profile_db.atl
    profile_tsb = profile_db.tsb

    # Get recent activities (last 7 days for quick stats, last 90 days for charts)
    recent_7d_db = db.query(Activity).filter(
        Activity.user_id == st.session_state.user["id"],
        Activity.start_date >= datetime.now() - timedelta(days=7)
    ).all()

    # Extract 7d data
    recent_7d = [
        {
            "start_date": a.start_date,
            "name": a.name,
            "duration": a.duration,
            "tss": a.tss,
            "normalized_power": a.normalized_power
        }
        for a in recent_7d_db
    ]

    recent_90d_db = db.query(Activity).filter(
        Activity.user_id == st.session_state.user["id"],
        Activity.start_date >= datetime.now() - timedelta(days=90)
    ).order_by(Activity.start_date).all()

    # Extract 90d data
    recent_90d = [
        {
            "start_date": a.start_date,
            "tss": a.tss or 0,
            "time_zone1": a.time_zone1,
            "time_zone2": a.time_zone2,
            "time_zone3": a.time_zone3,
            "time_zone4": a.time_zone4,
            "time_zone5": a.time_zone5,
            "time_zone6": a.time_zone6,
            "time_zone7": a.time_zone7
        }
        for a in recent_90d_db
    ]

# Training Load Overview
st.subheader("Training Load Overview")

col1, col2, col3, col4 = st.columns(4)

col1.metric("FTP", f"{profile_ftp:.0f}W")
col2.metric("CTL (Fitness)", f"{profile_ctl:.1f}")
col3.metric("ATL (Fatigue)", f"{profile_atl:.1f}")

tsb = profile_tsb
tsb_emoji = "🟢" if tsb > 5 else "🟡" if tsb > -10 else "🔴"
col4.metric("TSB (Form)", f"{tsb_emoji} {tsb:.1f}")

# Weekly TSS
tss_7d = sum(a["tss"] or 0 for a in recent_7d)
st.metric("7-Day TSS", f"{tss_7d:.0f}")

# Interpretation
if tsb > 5:
    st.success("Fresh and ready for hard training!")
elif tsb > -10:
    st.info("Optimal training zone - good balance")
else:
    st.warning("Fatigued - consider recovery or easy endurance")

st.markdown("---")

# Charts
if len(recent_90d) > 5:
    st.subheader("Performance Management Chart")
    st.plotly_chart(create_pmc_chart(recent_90d), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(create_weekly_tss_chart(recent_90d), use_container_width=True)
    with col2:
        st.plotly_chart(create_zone_distribution_chart(recent_90d), use_container_width=True)

    st.markdown("---")

    # Recent activities
    st.subheader("Recent Activities (Last 7 Days)")
    if recent_7d:
        data = [
            {
                "Date": a["start_date"].strftime("%Y-%m-%d"),
                "Name": a["name"],
                "Duration": f"{a['duration'] // 60}min",
                "TSS": round(a["tss"], 1) if a["tss"] else "N/A",
                "NP": round(a["normalized_power"], 0) if a["normalized_power"] else "N/A"
            }
            for a in sorted(recent_7d, key=lambda x: x["start_date"], reverse=True)
        ]
        st.dataframe(data, use_container_width=True)
    else:
        st.info("No activities in the last 7 days")
else:
    st.info("Sync more activities from the Analytics page to see charts (need at least 5 activities)")
