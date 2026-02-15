"""
Training Program page - Multi-week periodized training plans
"""
import streamlit as st
import sys
from pathlib import Path
import json
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.plan_agent import PlanAgent
from src.agent.workout_bridge import generate_planned_workout, validate_workout_constraints
from src.agent.workout_agent import safe_parse_number
from src.database.database import get_db
from src.database.models import TrainingProgram, WeekPlan, PlannedWorkout, Activity, WorkoutPlan, WorkoutFeedback
from src.visualization.charts import (
    create_program_timeline,
    create_planned_vs_actual_tss,
    create_program_progress_chart,
    create_workout_profile_chart,
)

st.set_page_config(page_title="Training Program", page_icon="📅", layout="wide")
st.title("📅 Training Program")

# Check if user is logged in
if "user" not in st.session_state:
    st.warning("Please connect your Strava account first!")
    st.stop()

if "profile" not in st.session_state or not st.session_state.profile.get("ftp"):
    st.warning("Please set your FTP in the Settings page first!")
    st.stop()

user_id = st.session_state.user["id"]

# Initialize session state for view management
if "program_view" not in st.session_state:
    st.session_state.program_view = "list"  # list, create, overview, week_detail

if "selected_program_id" not in st.session_state:
    st.session_state.selected_program_id = None

if "selected_week_number" not in st.session_state:
    st.session_state.selected_week_number = 1


# ============================================================================
# VIEW A: PROGRAM CREATION FORM
# ============================================================================
def show_create_program_form():
    st.subheader("Create New Training Program")
    st.markdown("Design a personalized multi-week training plan with periodization")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Goal")

        goal_type = st.selectbox(
            "Goal Type",
            ["Increase FTP", "Prepare for a race", "Build base fitness"],
        )

        goal_description = st.text_area(
            "Describe your goal",
            placeholder="e.g., I want to increase my FTP to 300W for summer racing season",
            height=100,
        )

        current_ftp = st.session_state.profile.get("ftp", 250)

        if goal_type == "Increase FTP":
            target_ftp = st.number_input(
                "Target FTP (watts)",
                min_value=int(current_ftp),
                max_value=500,
                value=int(current_ftp + 30),
                step=5,
            )
        else:
            target_ftp = None

        target_date = st.date_input(
            "Target Date",
            value=datetime.now() + timedelta(weeks=12),
            min_value=datetime.now() + timedelta(weeks=4),
            max_value=datetime.now() + timedelta(weeks=24),
        )

    with col2:
        st.markdown("### Volume")

        hours_per_week = st.slider(
            "Hours per week available",
            min_value=4.0,
            max_value=20.0,
            value=10.0,
            step=0.5,
        )

        sessions_per_week = st.slider(
            "Sessions per week",
            min_value=3,
            max_value=7,
            value=5,
        )

        st.markdown("### Current Fitness")
        st.metric("Current FTP", f"{current_ftp}W")
        st.metric("Current CTL", f"{st.session_state.profile.get('ctl', 0):.0f}")
        st.metric("Current TSB", f"{st.session_state.profile.get('tsb', 0):.1f}")

    st.markdown("---")

    col1, col2, col3 = st.columns([1, 1, 3])

    with col1:
        if st.button("Cancel", use_container_width=True):
            st.session_state.program_view = "list"
            st.rerun()

    with col2:
        create_button = st.button("Create Plan 🚀", use_container_width=True, type="primary")

    if create_button:
        if not goal_description:
            st.error("Please describe your goal")
            return

        # Build user input for PlanAgent
        user_input = f"""Goal: {goal_description}
Goal Type: {goal_type}
{"Target FTP: " + str(target_ftp) + "W" if target_ftp else ""}
Target Date: {target_date.strftime("%Y-%m-%d")}
Hours per week: {hours_per_week}
Sessions per week: {sessions_per_week}
"""

        with st.spinner("🤖 AI Coach is designing your training program... This may take 30-60 seconds."):
            try:
                # Get training history
                with get_db() as db:
                    activities = db.query(Activity).filter(
                        Activity.user_id == user_id
                    ).order_by(Activity.start_date.desc()).limit(90).all()

                    history = [{
                        "start_date": act.start_date.isoformat() if act.start_date else None,
                        "tss": act.tss or 0,
                        "duration": act.duration or 0,
                        "time_zone1": act.time_zone1 or 0,
                        "time_zone2": act.time_zone2 or 0,
                        "time_zone3": act.time_zone3 or 0,
                        "time_zone4": act.time_zone4 or 0,
                        "time_zone5": act.time_zone5 or 0,
                        "time_zone6": act.time_zone6 or 0,
                        "time_zone7": act.time_zone7 or 0,
                    } for act in activities]

                    feedback_history = []  # Not used for plan creation

                # Create program
                agent = PlanAgent()
                result = agent.create_program(
                    user_input=user_input,
                    user_profile=st.session_state.profile,
                    training_history=history,
                    feedback_history=feedback_history,
                )

                # Save to database
                with get_db() as db:
                    program = TrainingProgram(
                        user_id=user_id,
                        name=goal_description[:100],
                        goal_type=goal_type.lower().replace(" ", "_"),
                        goal_description=goal_description,
                        target_ftp=target_ftp,
                        target_date=datetime.combine(target_date, datetime.min.time()),
                        start_date=datetime.now(),
                        hours_per_week=hours_per_week,
                        sessions_per_week=sessions_per_week,
                        macro_plan_json=json.dumps(result["macro_plan"]),
                        initial_ftp=current_ftp,
                        initial_ctl=st.session_state.profile.get("ctl", 0),
                        status="active",
                    )
                    db.add(program)
                    db.flush()

                    # Create week plans
                    macro_plan = result["macro_plan"]
                    for week_target in macro_plan["week_targets"]:
                        week_num = week_target["week"]
                        phase = week_target["phase"]
                        target_tss = week_target["tss"]

                        # Find phase info
                        phase_info = next((p for p in macro_plan["phases"] if p["name"] == phase), None)
                        zone_focus = ",".join(phase_info["zone_focus"]) if phase_info else ""

                        week_start = datetime.now() + timedelta(weeks=week_num - 1)
                        week_end = week_start + timedelta(days=6)

                        # Build rich week instructions
                        focus_note = week_target.get("focus_note", "")
                        is_recovery = week_target.get("is_recovery", False)
                        week_label = f"Week {week_num} - {phase} phase"
                        if is_recovery:
                            week_label += " (Recovery Week)"
                        if focus_note:
                            week_label += f"\n{focus_note}"

                        week_plan = WeekPlan(
                            program_id=program.id,
                            week_number=week_num,
                            phase=phase,
                            target_tss=target_tss,
                            target_hours=hours_per_week,
                            target_sessions=sessions_per_week,
                            zone_focus=zone_focus,
                            week_instructions=week_label,
                            status="upcoming" if week_num > 1 else "current",
                            start_date=week_start,
                            end_date=week_end,
                        )
                        db.add(week_plan)

                    db.commit()

                    st.session_state.selected_program_id = program.id
                    st.session_state.program_view = "overview"
                    st.success("✅ Training program created successfully!")
                    st.rerun()

            except Exception as e:
                st.error(f"Failed to create program: {e}")
                import traceback
                st.code(traceback.format_exc())


# ============================================================================
# VIEW B: PROGRAM OVERVIEW (macro view)
# ============================================================================
def show_program_overview(program_id: int):
    with get_db() as db:
        program = db.query(TrainingProgram).filter(TrainingProgram.id == program_id).first()

        if not program:
            st.error("Program not found")
            return

        # Extract data from session (avoid DetachedInstanceError)
        program_data = {
            "id": program.id,
            "name": program.name,
            "goal_description": program.goal_description,
            "target_ftp": program.target_ftp,
            "target_date": program.target_date,
            "start_date": program.start_date,
            "hours_per_week": program.hours_per_week,
            "sessions_per_week": program.sessions_per_week,
            "initial_ftp": program.initial_ftp,
            "initial_ctl": program.initial_ctl,
            "status": program.status,
            "macro_plan_json": program.macro_plan_json,
        }

        week_plans = db.query(WeekPlan).filter(WeekPlan.program_id == program_id).order_by(WeekPlan.week_number).all()

        # Extract week plans data
        weeks_data = [{
            "id": wp.id,
            "week_number": wp.week_number,
            "phase": wp.phase,
            "target_tss": wp.target_tss,
            "actual_tss": wp.actual_tss,
            "status": wp.status,
            "actual_ctl": wp.actual_ctl,
        } for wp in week_plans]

    # Header
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        st.subheader(program_data["name"])
        st.caption(program_data["goal_description"])

    with col2:
        status_color = {"active": "🟢", "completed": "✅", "paused": "⏸️", "cancelled": "❌"}
        st.metric("Status", f"{status_color.get(program_data['status'], '')} {program_data['status'].upper()}")

    with col3:
        if st.button("← Back to Programs"):
            st.session_state.program_view = "list"
            st.rerun()

    st.markdown("---")

    # Progress metrics
    col1, col2, col3, col4 = st.columns(4)

    completed_weeks = len([w for w in weeks_data if w["status"] == "completed"])
    total_weeks = len(weeks_data)

    with col1:
        st.metric("Weeks Completed", f"{completed_weeks}/{total_weeks}")

    with col2:
        current_ftp = st.session_state.profile.get("ftp", 0)
        target_ftp = program_data.get("target_ftp")
        if target_ftp:
            st.metric("FTP Progress", f"{current_ftp}W → {target_ftp}W", delta=f"{current_ftp - program_data['initial_ftp']}W")
        else:
            st.metric("Current FTP", f"{current_ftp}W")

    with col3:
        days_remaining = (program_data["target_date"] - datetime.now()).days
        st.metric("Days Remaining", days_remaining)

    with col4:
        current_ctl = st.session_state.profile.get("ctl", 0)
        st.metric("Current CTL", f"{current_ctl:.0f}", delta=f"+{current_ctl - program_data['initial_ctl']:.0f}")

    # Progress bar
    progress = completed_weeks / total_weeks if total_weeks > 0 else 0
    st.progress(progress)

    st.markdown("---")

    # Program Rationale / Summary
    macro_plan = json.loads(program_data["macro_plan_json"])
    program_rationale = macro_plan.get("program_rationale", "")

    if program_rationale:
        st.subheader("Program Design Rationale")
        st.markdown(program_rationale)
        st.markdown("---")

    # Phase timeline
    st.subheader("Phase Timeline")
    try:
        timeline_fig = create_program_timeline(macro_plan)
        st.plotly_chart(timeline_fig, use_container_width=True)
    except Exception as e:
        st.error(f"Failed to create timeline: {e}")

    # Phase details
    if "phases" in macro_plan:
        with st.expander("Phase Details", expanded=False):
            for phase in macro_plan["phases"]:
                phase_name = phase.get("name", "Unknown")
                weeks_range = phase.get("weeks", [0, 0])
                zone_focus = phase.get("zone_focus", [])
                purpose = phase.get("purpose", "")
                key_workouts = phase.get("key_workouts", [])

                st.markdown(f"**{phase_name}** (Weeks {weeks_range[0]}-{weeks_range[1]})")
                if purpose:
                    st.caption(purpose)
                if zone_focus:
                    st.markdown(f"Zone Focus: {', '.join(zone_focus)}")
                if key_workouts:
                    st.markdown(f"Key Workouts: {', '.join(key_workouts)}")
                st.markdown("---")

    # Planned vs Actual TSS
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Weekly TSS")
        try:
            # Recreate WeekPlan objects from data for chart
            class MockWeekPlan:
                def __init__(self, data):
                    self.week_number = data["week_number"]
                    self.target_tss = data["target_tss"]
                    self.actual_tss = data["actual_tss"]
                    self.actual_ctl = data.get("actual_ctl")
                    self.phase = data["phase"]

            mock_weeks = [MockWeekPlan(w) for w in weeks_data]
            tss_fig = create_planned_vs_actual_tss(mock_weeks)
            st.plotly_chart(tss_fig, use_container_width=True)
        except Exception as e:
            st.error(f"Failed to create TSS chart: {e}")

    with col2:
        st.subheader("CTL Progression")
        try:
            # Recreate objects for chart
            class MockProgram:
                def __init__(self, data):
                    self.initial_ctl = data["initial_ctl"]
                    self.macro_plan_json = data["macro_plan_json"]

            mock_program = MockProgram(program_data)
            ctl_fig = create_program_progress_chart(mock_program, mock_weeks)
            st.plotly_chart(ctl_fig, use_container_width=True)
        except Exception as e:
            st.error(f"Failed to create CTL chart: {e}")

    st.markdown("---")

    # Current/Next week section
    st.subheader("Current Week")
    current_week = next((w for w in weeks_data if w["status"] == "current"), weeks_data[0] if weeks_data else None)

    if current_week:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Week", current_week["week_number"])
        with col2:
            st.metric("Phase", current_week["phase"])
        with col3:
            st.metric("Target TSS", f"{current_week['target_tss']:.0f}")
        with col4:
            if st.button("View Week Details →", use_container_width=True, type="primary"):
                st.session_state.selected_week_number = current_week["week_number"]
                st.session_state.program_view = "week_detail"
                st.rerun()


# ============================================================================
# VIEW C: CURRENT WEEK DETAIL
# ============================================================================
def show_week_detail(program_id: int, week_number: int):
    with get_db() as db:
        program = db.query(TrainingProgram).filter(TrainingProgram.id == program_id).first()
        week_plan = db.query(WeekPlan).filter(
            WeekPlan.program_id == program_id,
            WeekPlan.week_number == week_number
        ).first()

        if not week_plan:
            st.error("Week not found")
            return

        # Extract data
        program_data = {
            "id": program.id,
            "name": program.name,
            "hours_per_week": program.hours_per_week,
            "sessions_per_week": program.sessions_per_week,
        }

        week_data = {
            "week_number": week_plan.week_number,
            "phase": week_plan.phase,
            "target_tss": week_plan.target_tss,
            "zone_focus": week_plan.zone_focus,
            "week_instructions": week_plan.week_instructions,
            "adaptation_notes": week_plan.adaptation_notes,
            "actual_tss": week_plan.actual_tss,
            "status": week_plan.status,
        }

        planned_workouts = db.query(PlannedWorkout).filter(
            PlannedWorkout.week_plan_id == week_plan.id
        ).order_by(PlannedWorkout.day_index).all()

        workouts_data = [{
            "id": pw.id,
            "day_index": pw.day_index,
            "workout_type": pw.workout_type,
            "target_tss": pw.target_tss,
            "target_duration": pw.target_duration,
            "instructions": pw.instructions,
            "status": pw.status,
            "workout_plan_id": pw.workout_plan_id,
        } for pw in planned_workouts]

    # Header
    col1, col2 = st.columns([4, 1])

    with col1:
        st.subheader(f"Week {week_data['week_number']} - {week_data['phase']} Phase")

    with col2:
        if st.button("← Back to Overview"):
            st.session_state.program_view = "overview"
            st.rerun()

    # Week summary
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Target TSS", f"{week_data['target_tss']:.0f}")
    with col2:
        st.metric("Zone Focus", week_data["zone_focus"].replace(",", ", "))
    with col3:
        if week_data["actual_tss"]:
            st.metric("Actual TSS", f"{week_data['actual_tss']:.0f}",
                     delta=f"{week_data['actual_tss'] - week_data['target_tss']:.0f}")

    # Coaching notes
    if week_data["week_instructions"]:
        st.info(week_data["week_instructions"])

    if week_data["adaptation_notes"]:
        st.warning(f"⚠️ Adaptations: {week_data['adaptation_notes']}")

    st.markdown("---")

    # Generate workouts if needed
    if not workouts_data:
        st.warning("No workouts planned for this week yet.")

        if st.button("Plan Workouts for This Week"):
            with st.spinner("Planning workouts..."):
                try:
                    agent = PlanAgent()

                    with get_db() as db:
                        program = db.query(TrainingProgram).filter(TrainingProgram.id == program_id).first()
                        recent_weeks = db.query(WeekPlan).filter(
                            WeekPlan.program_id == program_id,
                            WeekPlan.week_number < week_number
                        ).order_by(WeekPlan.week_number.desc()).limit(3).all()

                        result = agent.plan_week(
                            program=program,
                            week_number=week_number,
                            user_profile=st.session_state.profile,
                            recent_weeks=recent_weeks,
                        )

                        # Save planned workouts
                        week_plan = db.query(WeekPlan).filter(
                            WeekPlan.program_id == program_id,
                            WeekPlan.week_number == week_number
                        ).first()

                        for workout_spec in result["week_detail"]["planned_workouts"]:
                            pw = PlannedWorkout(
                                week_plan_id=week_plan.id,
                                day_index=workout_spec["day_index"],
                                workout_type=workout_spec["workout_type"],
                                target_tss=workout_spec["target_tss"],
                                target_duration=workout_spec["target_duration"],
                                instructions=workout_spec["instructions"],
                                status="planned",
                            )
                            db.add(pw)

                        db.commit()
                        st.success("✅ Workouts planned!")
                        st.rerun()

                except Exception as e:
                    st.error(f"Failed to plan workouts: {e}")
        return

    # Display workouts
    st.subheader(f"Workouts ({len(workouts_data)} sessions)")

    for workout in workouts_data:
        with st.container():
            col1, col2, col3, col4 = st.columns([2, 1, 1, 2])

            with col1:
                status_icon = {"planned": "📋", "generated": "✅", "completed": "🏆", "skipped": "⏭️"}
                st.markdown(f"### {status_icon.get(workout['status'], '')} Workout {workout['day_index']}: {workout['workout_type']}")

            with col2:
                st.metric("TSS", f"~{workout['target_tss']:.0f}")

            with col3:
                st.metric("Duration", f"{workout['target_duration']}min")

            with col4:
                if workout["status"] == "planned":
                    if st.button(f"Generate .zwo", key=f"gen_{workout['id']}", use_container_width=True):
                        st.session_state[f"generating_{workout['id']}"] = True
                        st.rerun()

                elif workout["status"] == "generated":
                    if st.button(f"View Details", key=f"view_{workout['id']}", use_container_width=True):
                        # Toggle view state
                        key = f"show_details_{workout['id']}"
                        st.session_state[key] = not st.session_state.get(key, False)
                        st.rerun()

            # Show generation UI if triggered
            if st.session_state.get(f"generating_{workout['id']}", False):
                with st.spinner("Generating workout..."):
                    try:
                        # Get data for generation
                        with get_db() as db:
                            activities = db.query(Activity).filter(
                                Activity.user_id == user_id
                            ).order_by(Activity.start_date.desc()).limit(30).all()

                            history = [{
                                "start_date": act.start_date.isoformat() if act.start_date else None,
                                "tss": act.tss or 0,
                            } for act in activities]

                            feedbacks = db.query(WorkoutFeedback).filter(
                                WorkoutFeedback.user_id == user_id
                            ).order_by(WorkoutFeedback.created_at.desc()).limit(10).all()

                            feedback_history = [{
                                "workout_type": fb.workout_type,
                                "difficulty": fb.difficulty,
                                "rating": fb.rating,
                                "notes": fb.notes,
                            } for fb in feedbacks]

                            # Create PlannedWorkout object
                            planned_workout_obj = db.query(PlannedWorkout).filter(
                                PlannedWorkout.id == workout["id"]
                            ).first()

                            # Generate
                            result = generate_planned_workout(
                                planned_workout=planned_workout_obj,
                                user_profile=st.session_state.profile,
                                training_history=history,
                                feedback_history=feedback_history,
                            )

                            # Save WorkoutPlan
                            structure = result["structure"]
                            wp = WorkoutPlan(
                                user_id=user_id,
                                name=structure.get("NAME", workout["workout_type"]),
                                workout_type=structure.get("TYPE", workout["workout_type"]),
                                description=structure.get("RATIONALE", ""),
                                target_duration=int(safe_parse_number(structure.get("DURATION", workout["target_duration"]), workout["target_duration"])),
                                target_tss=safe_parse_number(structure.get("TSS", workout["target_tss"]), workout["target_tss"]),
                                intensity_factor=safe_parse_number(structure.get("IF", 0), 0),
                                interval_structure=structure.get("intervals", ""),
                                zwo_xml=result["workout_xml"],
                                user_request=workout["instructions"],
                                agent_reasoning=result["reasoning"],
                            )
                            db.add(wp)
                            db.flush()

                            # Link to PlannedWorkout
                            planned_workout_obj.workout_plan_id = wp.id
                            planned_workout_obj.status = "generated"
                            db.commit()

                            st.success("✅ Workout generated!")
                            st.session_state[f"generating_{workout['id']}"] = False
                            st.rerun()

                    except Exception as e:
                        st.error(f"Failed to generate: {e}")
                        st.session_state[f"generating_{workout['id']}"] = False

            # Show full workout details if generated and view is toggled
            if workout["status"] == "generated" and st.session_state.get(f"show_details_{workout['id']}", False):
                try:
                    with get_db() as db:
                        workout_plan = db.query(WorkoutPlan).filter(
                            WorkoutPlan.id == workout["workout_plan_id"]
                        ).first()

                        if workout_plan:
                            st.markdown("---")
                            st.markdown(f"### 📋 {workout_plan.name}")

                            # Metrics row
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Type", workout_plan.workout_type or "N/A")
                            col2.metric("TSS", f"{workout_plan.target_tss:.0f}" if workout_plan.target_tss else "N/A")
                            col3.metric("IF", f"{workout_plan.intensity_factor:.2f}" if workout_plan.intensity_factor else "N/A")

                            # Rationale
                            if workout_plan.description:
                                st.markdown("**Why This Workout?**")
                                st.info(workout_plan.description)

                            # Power profile chart
                            if workout_plan.zwo_xml:
                                st.markdown("**Power Profile**")
                                try:
                                    # Parse intervals from agent reasoning or reconstruct from XML
                                    from src.agent.workout_agent import WorkoutAgent
                                    agent = WorkoutAgent()

                                    # Extract intervals from workout structure stored in interval_structure
                                    intervals_text = workout_plan.interval_structure
                                    if intervals_text:
                                        intervals = agent._parse_intervals(intervals_text)
                                        ftp = st.session_state.profile.get("ftp", 250)
                                        profile_fig = create_workout_profile_chart(intervals, ftp)
                                        st.plotly_chart(profile_fig, use_container_width=True)
                                except Exception as e:
                                    st.warning(f"Could not display power profile: {e}")

                            # Workout structure
                            with st.expander("Workout Structure", expanded=False):
                                st.code(workout_plan.interval_structure or "No structure available")

                            # Download .zwo
                            st.markdown("**Download Workout**")
                            col1, col2 = st.columns([2, 1])

                            with col1:
                                filename = f"{workout_plan.name.replace(' ', '_')}.zwo"
                                st.download_button(
                                    label="⬇️ Download .zwo File",
                                    data=workout_plan.zwo_xml,
                                    file_name=filename,
                                    mime="application/xml",
                                    key=f"download_{workout['id']}",
                                    use_container_width=True,
                                )

                            with col2:
                                if st.button("Hide Details", key=f"hide_{workout['id']}", use_container_width=True):
                                    st.session_state[f"show_details_{workout['id']}"] = False
                                    st.rerun()

                            # Preview XML
                            with st.expander("Preview .zwo XML"):
                                st.code(workout_plan.zwo_xml, language="xml")

                            # Reasoning
                            if workout_plan.agent_reasoning:
                                with st.expander("AI Coach Reasoning"):
                                    st.text(workout_plan.agent_reasoning)

                except Exception as e:
                    st.error(f"Failed to load workout details: {e}")

            st.markdown("---")


# ============================================================================
# MAIN VIEW ROUTER
# ============================================================================

# Check for active program
with get_db() as db:
    active_programs = db.query(TrainingProgram).filter(
        TrainingProgram.user_id == user_id,
        TrainingProgram.status == "active"
    ).all()

    programs_list = [{
        "id": p.id,
        "name": p.name,
        "target_date": p.target_date,
        "status": p.status,
    } for p in active_programs]

# Route to appropriate view
if st.session_state.program_view == "create":
    show_create_program_form()

elif st.session_state.program_view == "overview":
    if st.session_state.selected_program_id:
        show_program_overview(st.session_state.selected_program_id)
    else:
        st.session_state.program_view = "list"
        st.rerun()

elif st.session_state.program_view == "week_detail":
    if st.session_state.selected_program_id:
        show_week_detail(st.session_state.selected_program_id, st.session_state.selected_week_number)
    else:
        st.session_state.program_view = "list"
        st.rerun()

else:  # list view
    if not programs_list:
        st.info("You don't have any training programs yet. Create your first one!")

        if st.button("Create Training Program", type="primary"):
            st.session_state.program_view = "create"
            st.rerun()

    else:
        st.subheader("Your Training Programs")

        for prog in programs_list:
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    st.markdown(f"### {prog['name']}")
                    st.caption(f"Target: {prog['target_date'].strftime('%B %d, %Y')}")

                with col2:
                    st.metric("Status", prog["status"].upper())

                with col3:
                    if st.button("View", key=f"view_{prog['id']}", use_container_width=True):
                        st.session_state.selected_program_id = prog["id"]
                        st.session_state.program_view = "overview"
                        st.rerun()

                st.markdown("---")

        if st.button("+ Create New Program", type="primary"):
            st.session_state.program_view = "create"
            st.rerun()
