"""
Generate Workout page - AI-powered workout generation with expert coaching
"""
import streamlit as st
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.workout_agent import WorkoutAgent, safe_parse_number
from src.database.database import get_db
from src.database.models import Activity, WorkoutPlan, WorkoutFeedback
from src.visualization.charts import create_workout_profile_chart
from datetime import datetime, timedelta

st.title("Generate Workout")


def _infer_workout_type(workout_request: str, focus_area: str) -> str:
    """Infer the workout type from the user request and focus area selection."""
    if focus_area and focus_area != "Auto (let AI decide)":
        # Map UI labels to internal types
        type_map = {
            "Endurance": "Endurance",
            "Tempo": "Tempo",
            "Sweet Spot": "Sweet Spot",
            "Threshold": "Threshold",
            "VO2max": "VO2max",
            "Anaerobic/Sprint": "Anaerobic",
            "Force/SFR": "Force",
            "Recovery": "Recovery",
        }
        return type_map.get(focus_area, focus_area)

    # Keyword matching for presets and free-text
    request_lower = workout_request.lower()
    type_keywords = {
        "Recovery": ["recovery", "easy", "recup", "recuperation"],
        "Endurance": ["endurance", "z2", "zone 2", "base", "aerobic"],
        "Tempo": ["tempo", "z3", "zone 3"],
        "Sweet Spot": ["sweet spot", "sweetspot", "ss"],
        "Threshold": ["threshold", "ftp", "seuil", "z4", "zone 4"],
        "VO2max": ["vo2", "vo2max", "high intensity", "hiit"],
        "Anaerobic": ["anaerobic", "sprint", "neuromuscular", "tabata", "micro-burst"],
        "Force": ["force", "sfr", "strength", "low cadence", "torque"],
    }
    for wtype, keywords in type_keywords.items():
        if any(kw in request_lower for kw in keywords):
            return wtype
    return ""  # Unknown


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
        st.session_state.workout_input = "Easy 1 hour recovery ride"

with col2:
    if st.button("Sweet Spot", use_container_width=True):
        st.session_state.workout_input = "90 minute sweet spot workout"

with col3:
    if st.button("VO2max", use_container_width=True):
        st.session_state.workout_input = "High intensity VO2max intervals"

with col4:
    if st.button("Threshold", use_container_width=True):
        st.session_state.workout_input = "FTP threshold intervals"

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("Sprint/Anaerobic", use_container_width=True):
        st.session_state.workout_input = "Sprint and anaerobic power training"

with col2:
    if st.button("Force/SFR", use_container_width=True):
        st.session_state.workout_input = "Low cadence strength force reps SFR workout"

with col3:
    if st.button("Tempo", use_container_width=True):
        st.session_state.workout_input = "Tempo endurance ride at zone 3"

with col4:
    if st.button("Endurance", use_container_width=True):
        st.session_state.workout_input = "Long endurance base ride zone 2"

st.markdown("---")

# Custom input
workout_request = st.text_area(
    "Or describe your ideal workout:",
    value=st.session_state.get("workout_input", ""),
    placeholder="Example: 90 min with over-under sweet spot intervals, or Billats 30/30 VO2max session...",
    height=100
)

# Additional context
with st.expander("Advanced Options"):
    col1, col2 = st.columns(2)

    with col1:
        focus_area = st.selectbox(
            "Focus Area",
            ["Auto (let AI decide)", "Endurance", "Tempo", "Sweet Spot", "Threshold",
             "VO2max", "Anaerobic/Sprint", "Force/SFR", "Recovery"]
        )

    with col2:
        duration_hint = st.slider(
            "Target Duration (minutes)",
            30, 180, 90, 15
        )

    additional_notes = st.text_input(
        "Additional notes (optional)",
        placeholder="e.g., I prefer longer intervals, want to try over-unders, need low cadence work..."
    )

# Display current fitness
st.markdown("---")
st.subheader("Your Current Fitness")

profile = st.session_state.profile
col1, col2, col3, col4 = st.columns(4)
col1.metric("FTP", f"{profile['ftp']:.0f}W")
col2.metric("CTL (Fitness)", f"{profile['ctl']:.1f}")
col3.metric("ATL (Fatigue)", f"{profile['atl']:.1f}")

tsb = profile['tsb']
tsb_color = "🟢" if tsb > 5 else "🟡" if tsb > -10 else "🔴"
col4.metric("TSB (Form)", f"{tsb_color} {tsb:.1f}")

if tsb > 5:
    st.info("Fresh and ready for hard training!")
elif tsb > -10:
    st.info("Optimal training zone - good balance of fitness and freshness")
else:
    st.warning("Fatigued - consider recovery or easy endurance")

# Generate button
st.markdown("---")

if st.button("Generate Workout", type="primary", use_container_width=True):
    if not workout_request.strip():
        st.error("Please describe what kind of workout you want!")
        st.stop()

    with st.spinner("AI coach is designing your workout..."):
        try:
            # Infer workout type for context-aware processing
            target_type = _infer_workout_type(workout_request, focus_area)

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

            # Get feedback history - TYPE-AWARE retrieval
            with get_db() as db:
                if target_type:
                    # Type-specific feedback (most relevant, up to 7)
                    type_feedbacks = db.query(WorkoutFeedback, WorkoutPlan).join(
                        WorkoutPlan, WorkoutFeedback.workout_id == WorkoutPlan.id
                    ).filter(
                        WorkoutFeedback.user_id == st.session_state.user["id"],
                        WorkoutFeedback.workout_type == target_type
                    ).order_by(WorkoutFeedback.created_at.desc()).limit(7).all()

                    # General feedback from OTHER types (up to 3)
                    general_feedbacks = db.query(WorkoutFeedback, WorkoutPlan).join(
                        WorkoutPlan, WorkoutFeedback.workout_id == WorkoutPlan.id
                    ).filter(
                        WorkoutFeedback.user_id == st.session_state.user["id"],
                        WorkoutFeedback.workout_type != target_type
                    ).order_by(WorkoutFeedback.created_at.desc()).limit(3).all()
                else:
                    type_feedbacks = []
                    general_feedbacks = db.query(WorkoutFeedback, WorkoutPlan).join(
                        WorkoutPlan, WorkoutFeedback.workout_id == WorkoutPlan.id
                    ).filter(
                        WorkoutFeedback.user_id == st.session_state.user["id"]
                    ).order_by(WorkoutFeedback.created_at.desc()).limit(10).all()

                feedback_history = []
                for fb, wp in type_feedbacks:
                    feedback_history.append({
                        "workout_name": wp.name,
                        "workout_type": wp.workout_type or "Unknown",
                        "difficulty": fb.difficulty,
                        "rating": fb.rating,
                        "notes": fb.notes,
                        "is_same_type": True,
                    })
                for fb, wp in general_feedbacks:
                    feedback_history.append({
                        "workout_name": wp.name,
                        "workout_type": wp.workout_type or "Unknown",
                        "difficulty": fb.difficulty,
                        "rating": fb.rating,
                        "notes": fb.notes,
                        "is_same_type": False,
                    })

            # Build profile with target type
            profile_with_context = {**profile, "target_workout_type": target_type}

            # Generate workout
            agent = WorkoutAgent()
            result = agent.generate_workout(
                user_input=final_request,
                user_profile=profile_with_context,
                training_history=history,
                feedback_history=feedback_history
            )

            # Save workout to database
            duration_int = int(safe_parse_number(result["structure"].get("DURATION", 0), 0))
            target_tss = safe_parse_number(result["structure"].get("TSS", 0), 0)
            intensity_factor = safe_parse_number(result["structure"].get("IF", 0), 0)

            with get_db() as db:
                workout_plan = WorkoutPlan(
                    user_id=st.session_state.user["id"],
                    name=result["structure"].get("NAME", "Workout"),
                    workout_type=result["structure"].get("TYPE", "Unknown"),
                    description=result["structure"].get("RATIONALE", ""),
                    target_duration=duration_int,
                    target_tss=target_tss,
                    intensity_factor=intensity_factor,
                    interval_structure=result["structure"].get("intervals", ""),
                    zwo_xml=result["workout_xml"],
                    user_request=final_request,
                    agent_reasoning=result["reasoning"]
                )
                db.add(workout_plan)
                db.commit()
                result["workout_id"] = workout_plan.id

            # Store in session state
            st.session_state.generated_workout = result

            st.success("Workout generated successfully!")

        except Exception as e:
            st.error(f"Error generating workout: {e}")
            import traceback
            st.code(traceback.format_exc())

# Display generated workout
if "generated_workout" in st.session_state:
    st.markdown("---")
    st.subheader("Your Personalized Workout")

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

    # Cadence notes
    cadence_notes = structure.get("CADENCE_NOTES", "")
    if cadence_notes:
        st.markdown("**Cadence Targets:**")
        st.success(cadence_notes)

    # Power Profile Chart
    st.markdown("**Power Profile**")
    try:
        intervals_text = structure.get("intervals", "")
        if intervals_text:
            agent = WorkoutAgent()
            intervals = agent._parse_intervals(intervals_text)
            ftp = st.session_state.profile.get("ftp", 250)
            profile_fig = create_workout_profile_chart(intervals, ftp)
            st.plotly_chart(profile_fig, use_container_width=True)
        else:
            st.warning("No interval data available for power profile")
    except Exception as e:
        st.warning(f"Could not display power profile: {e}")

    # Intervals
    with st.expander("Workout Structure", expanded=False):
        st.code(structure.get("intervals", structure.get("STRUCTURE", "No structure available")))

    # Reasoning
    with st.expander("AI Reasoning (debug)", expanded=False):
        reasoning = result.get("reasoning", "No reasoning available")
        st.code(reasoning, language="text")

    # Download .zwo
    st.markdown("---")
    st.subheader("Download for Zwift/Wahoo")

    zwo_xml = result.get("workout_xml", "")

    if zwo_xml:
        col1, col2 = st.columns([2, 1])

        with col1:
            filename = f"{structure.get('NAME', 'workout').replace(' ', '_')}.zwo"
            st.download_button(
                label="Download .zwo File",
                data=zwo_xml,
                file_name=filename,
                mime="application/xml",
                type="primary",
                use_container_width=True
            )

        with col2:
            if st.button("Generate New Workout", use_container_width=True):
                del st.session_state.generated_workout
                st.rerun()

        # Preview XML
        with st.expander("Preview .zwo File"):
            st.code(zwo_xml, language="xml")

        # Feedback section
        st.markdown("---")
        st.subheader("How was this workout?")
        st.info("Your feedback helps the AI learn your preferences!")

        col1, col2 = st.columns(2)

        with col1:
            difficulty = st.select_slider(
                "Difficulty",
                options=["too_easy", "perfect", "too_hard"],
                value="perfect"
            )

        with col2:
            rating = st.slider("Rating", 1, 5, 3)

        notes = st.text_area(
            "Notes (optional)",
            placeholder="e.g., I prefer longer intervals, great workout, too many short efforts..."
        )

        if st.button("Submit Feedback", type="primary"):
            with get_db() as db:
                feedback = WorkoutFeedback(
                    workout_id=result.get("workout_id"),
                    user_id=st.session_state.user["id"],
                    rating=rating,
                    difficulty=difficulty,
                    notes=notes,
                    workout_type=result.get("structure", {}).get("TYPE", None),
                )
                db.add(feedback)
                db.commit()

            st.success("Feedback saved! The AI will use this to improve future workouts.")
            st.balloons()

    else:
        st.error("No .zwo file generated")
