"""
Dashboard page - Overview of training metrics and recent activities
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.title("🏠 Dashboard")

# Check if user is logged in
if "user" not in st.session_state:
    st.warning("Please connect your Strava account from the Analytics page first.")
    st.stop()

# Placeholder for Phase 1
st.info(
    "Dashboard visualizations will be fully implemented in Phase 2-3. For now, this is a placeholder."
)

# Mock data for demonstration
st.subheader("Training Load Overview")

col1, col2, col3, col4 = st.columns(4)
col1.metric("FTP", "265W", "+5W")
col2.metric("CTL", "85", "+2")
col3.metric("TSB", "-15", delta="-3", delta_color="inverse")
col4.metric("7d TSS", "450", "+10%")

# Placeholder charts
st.subheader("Performance Management Chart")
st.markdown("*CTL/ATL/TSB trends will be displayed here once activities are synced*")

# Sample chart structure
dates = pd.date_range(end=datetime.now(), periods=90)
fig = go.Figure()
fig.add_trace(
    go.Scatter(x=dates, y=[85] * 90, mode="lines", name="CTL", line=dict(color="blue"))
)
fig.add_trace(
    go.Scatter(x=dates, y=[70] * 90, mode="lines", name="ATL", line=dict(color="red"))
)
fig.update_layout(title="Training Load (Last 90 Days)", xaxis_title="Date", yaxis_title="Load")
st.plotly_chart(fig, use_container_width=True)

# Recent activities placeholder
st.subheader("Recent Activities")
st.markdown("*Your recent Strava activities will appear here after syncing*")
