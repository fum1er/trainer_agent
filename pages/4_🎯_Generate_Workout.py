"""
Generate Workout page - AI-powered workout generation
"""
import streamlit as st
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.workout_agent import WorkoutAgent
from src.database.database import get_db
from src.database.models import Activity
from datetime import datetime, timedelta

st.title("🎯 Generate Workout")

# Check if user is logged in
if "user" not in st.session_state:
    st.warning("Please connect your Strava account first!")
    st.stop()

# Check if profile exists
if "profile" not in st.session_state or not st.session_state.profile.get("ftp"):
    st.warning("Please set your FTP in the Settings page first!")
    st.stop()

st.markdown("---")

# Workout generation interface
st.subheader("What do you want to train today?")

# Quick presets
st.markdown("**Quick Presets:**")
col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("Recovery Ride", use_container_width=True):
        st.session_state.workout_input = "Easy 1 hour recovery ride at endurance pace"

with col2:
    if st.button("Sweet Spot", use_container_width=True):
        st.session_state.workout_input = "90 minute sweet spot workout with 3x12min intervals"

with col3:
    if st.button("VO2max", use_container_width=True):
        st.session_state.workout_input = "High intensity VO2max intervals, 5x5min at 110-120% FTP"

with col4:
    if st.button("Threshold", use_container_width=True):
        st.session_state.workout_input = "FTP intervals, 2x20min at threshold"

st.markdown("---")

# Custom input
workout_request = st.text_area(
    "Or describe your ideal workout:",
    value=st.session_state.get("workout_input", ""),
    placeholder="Example: 90 minute sweet spot ride with 3 intervals...",
    height=100
)

# Additional context
with st.expander("⚙️ Advanced Options"):
    col1, col2 = st.columns(2)

    with col1:
        focus_area = st.selectbox(
            "Focus Area",
            ["Auto (let AI decide)", "Endurance", "Sweet Spot", "Threshold", "VO2max", "Recovery"]
        )

    with col2:
        duration_hint = st.slider(
            "Target Duration (minutes)",
            30, 180, 90, 15
        )

    additional_notes = st.text_input(
        "Additional notes (optional)",
        placeholder="e.g., I prefer longer intervals, avoid short VO2 bursts..."
    )

# Display current fitness
st.markdown("---")
st.subheader("📊 Your Current Fitness")

profile = st.session_state.profile
col1, col2, col3, col4 = st.columns(4)
col1.metric("FTP", f"{profile['ftp']:.0f}W")
col2.metric("CTL (Fitness)", f"{profile['ctl']:.1f}")
col3.metric("ATL (Fatigue)", f"{profile['atl']:.1f}")

tsb = profile['tsb']
tsb_color = "🟢" if tsb > 5 else "🟡" if tsb > -10 else "🔴"
col4.metric("TSB (Form)", f"{tsb_color} {tsb:.1f}")

# Interpretation
if tsb > 5:
    st.info("✅ Fresh and ready for hard training!")
elif tsb > -10:
    st.info("💪 Optimal training zone - good balance of fitness and freshness")
else:
    st.warning("⚠️ Fatigued - consider recovery or easy endurance")

# Generate button
st.markdown("---")

if st.button("🚀 Generate Workout", type="primary", use_container_width=True):
    if not workout_request.strip():
        st.error("Please describe what kind of workout you want!")
        st.stop()

    with st.spinner("🧠 AI is designing your perfect workout..."):
        try:
            # Prepare input
            final_request = workout_request
            if focus_area != "Auto (let AI decide)":
                final_request += f" Focus: {focus_area}."
            if duration_hint:
                final_request += f" Target duration: {duration_hint} minutes."
            if additional_notes:
                final_request += f" Notes: {additional_notes}"

            # Get recent activities
            with get_db() as db:
                recent_activities = db.query(Activity).filter(
                    Activity.user_id == st.session_state.user["id"],
                    Activity.start_date >= datetime.now() - timedelta(days=7)
                ).order_by(Activity.start_date.desc()).limit(10).all()

                history = [
                    {
                        "date": act.start_date.strftime("%Y-%m-%d"),
                        "name": act.name,
                        "duration": act.duration // 60,
                        "tss": act.tss
                    }
                    for act in recent_activities
                ]

            # Generate workout
            agent = WorkoutAgent()
            result = agent.generate_workout(
                user_input=final_request,
                user_profile=profile,
                training_history=history
            )

            # Store in session state
            st.session_state.generated_workout = result

            st.success("✅ Workout generated successfully!")

        except Exception as e:
            st.error(f"Error generating workout: {e}")
            import traceback
            st.code(traceback.format_exc())

# Display generated workout
if "generated_workout" in st.session_state:
    st.markdown("---")
    st.subheader("🎉 Your Personalized Workout")

    result = st.session_state.generated_workout

    # Workout structure
    structure = result.get("structure", {})

    col1, col2, col3 = st.columns(3)
    col1.metric("Workout", structure.get("NAME", "N/A"))
    col2.metric("Type", structure.get("TYPE", "N/A"))
    col3.metric("Duration", f"{structure.get('DURATION', 'N/A')} min")

    col1, col2 = st.columns(2)
    col1.metric("Target TSS", structure.get("TSS", "N/A"))
    col2.metric("Intensity Factor", structure.get("IF", "N/A"))

    # Rationale
    st.markdown("**Why This Workout?**")
    st.info(structure.get("RATIONALE", "No rationale available"))

    # Intervals
    with st.expander("📋 Workout Structure", expanded=True):
        st.code(structure.get("intervals", structure.get("STRUCTURE", "No structure available")))

    # Reasoning
    with st.expander("🧠 AI Reasoning"):
        st.text(result.get("reasoning", "No reasoning available"))

    # Download .zwo
    st.markdown("---")
    st.subheader("📥 Download for Zwift/Wahoo")

    zwo_xml = result.get("workout_xml", "")

    if zwo_xml:
        col1, col2 = st.columns([2, 1])

        with col1:
            filename = f"{structure.get('NAME', 'workout').replace(' ', '_')}.zwo"
            st.download_button(
                label="⬇️ Download .zwo File",
                data=zwo_xml,
                file_name=filename,
                mime="application/xml",
                type="primary",
                use_container_width=True
            )

        with col2:
            if st.button("🔄 Generate New Workout", use_container_width=True):
                del st.session_state.generated_workout
                st.rerun()

        # Preview XML
        with st.expander("👁️ Preview .zwo File"):
            st.code(zwo_xml, language="xml")
    else:
        st.error("No .zwo file generated")
