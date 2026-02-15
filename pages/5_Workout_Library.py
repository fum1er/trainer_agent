"""
Workout Library - Browse and manage generated workouts
"""
import streamlit as st
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.database import get_db
from src.database.models import WorkoutPlan, WorkoutFeedback
from datetime import datetime

st.title("Workout Library")

# Check if user is logged in
if "user" not in st.session_state:
    st.warning("Please connect your Strava account first!")
    st.stop()

st.markdown("---")

# Filters
col1, col2, col3 = st.columns(3)

with col1:
    filter_type = st.selectbox(
        "Filter by Type",
        ["All", "Recovery", "Endurance", "Sweet Spot", "Threshold", "VO2max"]
    )

with col2:
    filter_tss = st.slider("Max TSS", 0, 200, 200)

with col3:
    sort_by = st.selectbox("Sort by", ["Date (newest)", "Date (oldest)", "TSS (high to low)", "Rating"])

# Get workouts
with get_db() as db:
    query = db.query(WorkoutPlan, WorkoutFeedback).outerjoin(
        WorkoutFeedback, WorkoutPlan.id == WorkoutFeedback.workout_id
    ).filter(WorkoutPlan.user_id == st.session_state.user["id"])

    # Apply filters
    if filter_type != "All":
        query = query.filter(WorkoutPlan.workout_type == filter_type)

    if filter_tss < 200:
        query = query.filter(WorkoutPlan.target_tss <= filter_tss)

    # Apply sorting
    if sort_by == "Date (newest)":
        query = query.order_by(WorkoutPlan.created_at.desc())
    elif sort_by == "Date (oldest)":
        query = query.order_by(WorkoutPlan.created_at.asc())
    elif sort_by == "TSS (high to low)":
        query = query.order_by(WorkoutPlan.target_tss.desc())
    elif sort_by == "Rating":
        query = query.order_by(WorkoutFeedback.rating.desc())

    workouts_db = query.all()

    # Extract data within session to avoid DetachedInstanceError
    workouts = []
    for wp, fb in workouts_db:
        workout_data = {
            "id": wp.id,
            "name": wp.name,
            "workout_type": wp.workout_type,
            "created_at": wp.created_at,
            "target_tss": wp.target_tss,
            "target_duration": wp.target_duration,
            "description": wp.description,
            "interval_structure": wp.interval_structure,
            "zwo_xml": wp.zwo_xml,
            "user_request": wp.user_request
        }
        feedback_data = None
        if fb:
            feedback_data = {
                "rating": fb.rating,
                "difficulty": fb.difficulty,
                "notes": fb.notes
            }
        workouts.append((workout_data, feedback_data))

if not workouts:
    st.info("No workouts found. Generate your first workout on the Generate Workout page!")
    st.stop()

st.markdown(f"**Found {len(workouts)} workouts**")
st.markdown("---")

# Display workouts
for workout_data, feedback_data in workouts:
    with st.container():
        col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

        with col1:
            st.markdown(f"### {workout_data['name']}")
            st.caption(f"{workout_data['workout_type']} | {workout_data['created_at'].strftime('%Y-%m-%d')}")

        with col2:
            st.metric("TSS", f"{workout_data['target_tss']:.0f}")

        with col3:
            st.metric("Duration", f"{workout_data['target_duration']}min")

        with col4:
            if feedback_data and feedback_data['rating']:
                stars = "⭐" * feedback_data['rating']
                st.markdown(f"**{stars}**")
            else:
                st.markdown("No rating")

        # Description
        if workout_data['description']:
            with st.expander("Why this workout?"):
                st.info(workout_data['description'])

        # Structure
        with st.expander("Workout Structure"):
            st.code(workout_data['interval_structure'])

        # Feedback
        if feedback_data:
            with st.expander("Your Feedback"):
                st.write(f"**Difficulty**: {feedback_data['difficulty']}")
                if feedback_data['notes']:
                    st.write(f"**Notes**: {feedback_data['notes']}")

        # Actions
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(f"Download .zwo", key=f"download_{workout_data['id']}"):
                filename = f"{workout_data['name'].replace(' ', '_')}.zwo"
                st.download_button(
                    label="Click to download",
                    data=workout_data['zwo_xml'],
                    file_name=filename,
                    mime="application/xml",
                    key=f"dl_btn_{workout_data['id']}"
                )

        with col2:
            if st.button(f"Re-generate Similar", key=f"regen_{workout_data['id']}"):
                st.session_state.workout_input = workout_data['user_request']
                st.switch_page("pages/4_Generate_Workout.py")

        with col3:
            if st.button(f"Delete", key=f"delete_{workout_data['id']}", type="secondary"):
                with get_db() as db:
                    db.query(WorkoutPlan).filter(WorkoutPlan.id == workout_data['id']).delete()
                    db.commit()
                st.success("Workout deleted!")
                st.rerun()

        st.markdown("---")
