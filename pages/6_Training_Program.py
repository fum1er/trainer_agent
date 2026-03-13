"""
Training Program page — Multi-week periodized training plan with:
  • Plan review & per-week validation flow
  • Calendar view
  • Batch .zwo generation after approval
  • Alternative workout generation
  • Adaptive re-planning (Strava actuals vs plan)
  • TrainingPeaks sync
"""
import json
import traceback
import sys
from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.database import get_db
from src.database.models import (
    TrainingProgram, WeekPlan, PlannedWorkout, WorkoutPlan, WorkoutFeedback, Activity,
)
from src.agent.plan_agent import PlanAgent
from src.agent.workout_bridge import generate_planned_workout, batch_generate_week_workouts
from src.agent.adaptation import AdaptationEngine
from src.utils.session_init import init_session
from src.visualization.charts import (
    create_program_timeline, create_planned_vs_actual_tss, create_program_progress_chart,
    create_workout_profile_chart,
)
from src.agent.workout_agent import WorkoutAgent

try:
    from src.trainingpeaks.client import TrainingPeaksClient
    _TP_AVAILABLE = True
except ImportError:
    _TP_AVAILABLE = False

# ── Safe helper (needed for parsing LLM output) ───────────────────────────────
def safe_parse_number(value, default=0.0):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        import re
        m = re.search(r"[-+]?\d*\.?\d+", str(value))
        return float(m.group()) if m else default
    except Exception:
        return default

# ── Workout-type colors for calendar ─────────────────────────────────────────
_TYPE_COLOR = {
    "Recovery":    "#6cb4e4",
    "Endurance":   "#57cc99",
    "Tempo":       "#ffd166",
    "Sweet Spot":  "#f4a261",
    "Threshold":   "#e76f51",
    "VO2max":      "#e63946",
    "Anaerobic":   "#9b2226",
    "Force":       "#8338ec",
}

st.set_page_config(page_title="Training Program", page_icon="📅", layout="wide")
st.title("📅 Training Program")

init_session()

if "user" not in st.session_state:
    st.warning("Please connect your Strava account from the Dashboard first!")
    st.stop()
if "profile" not in st.session_state or not st.session_state.profile.get("ftp"):
    st.warning("Please set your FTP in the Settings page first!")
    st.stop()

user_id = st.session_state.user["id"]

# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [
    ("program_view", "list"),
    ("selected_program_id", None),
    ("selected_week_number", 1),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _load_common_data(program_id):
    """Return (program_data dict, weeks_data list) safely."""
    with get_db() as db:
        prog = db.query(TrainingProgram).filter(TrainingProgram.id == program_id).first()
        if not prog:
            return None, []
        program_data = {
            "id": prog.id, "name": prog.name,
            "goal_description": prog.goal_description,
            "target_ftp": prog.target_ftp, "target_date": prog.target_date,
            "start_date": prog.start_date, "status": prog.status,
            "hours_per_week": prog.hours_per_week,
            "sessions_per_week": prog.sessions_per_week,
            "macro_plan_json": prog.macro_plan_json,
            "initial_ftp": prog.initial_ftp or 0,
            "initial_ctl": prog.initial_ctl or 0,
        }
        weeks_data = []
        for w in prog.week_plans:
            pws = db.query(PlannedWorkout).filter(
                PlannedWorkout.week_plan_id == w.id
            ).order_by(PlannedWorkout.day_index).all()
            weeks_data.append({
                "id": w.id, "week_number": w.week_number,
                "phase": w.phase, "target_tss": w.target_tss,
                "target_hours": w.target_hours, "target_sessions": w.target_sessions,
                "zone_focus": w.zone_focus or "",
                "week_instructions": w.week_instructions or "",
                "adaptation_notes": w.adaptation_notes or "",
                "actual_tss": w.actual_tss, "actual_ctl": w.actual_ctl,
                "actual_atl": w.actual_atl, "actual_tsb": w.actual_tsb,
                "status": w.status, "start_date": w.start_date,
                "planned_workouts": [{
                    "id": pw.id, "day_index": pw.day_index,
                    "workout_type": pw.workout_type,
                    "target_tss": pw.target_tss,
                    "target_duration": pw.target_duration,
                    "instructions": pw.instructions or "",
                    "status": pw.status,
                    "workout_plan_id": pw.workout_plan_id,
                } for pw in pws],
            })
    return program_data, weeks_data


def _generate_workout_slots_for_week(week_plan_id, week_data, program_data):
    """Use AdaptationEngine to generate PlannedWorkout slots for a week (fast, no LLM)."""
    engine = AdaptationEngine()
    zone_focus = [z.strip() for z in week_data["zone_focus"].split(",") if z.strip()]
    slots = engine.adjust_week_distribution(
        target_tss=week_data["target_tss"],
        sessions_per_week=program_data["sessions_per_week"],
        zone_focus=zone_focus,
        current_profile=st.session_state.profile,
    )
    with get_db() as db:
        week_plan = db.query(WeekPlan).filter(WeekPlan.id == week_plan_id).first()
        for slot in slots:
            db.add(PlannedWorkout(
                week_plan_id=week_plan_id,
                day_index=slot["day_index"],
                workout_type=slot["workout_type"],
                target_tss=slot["target_tss"],
                target_duration=slot["target_duration"],
                instructions=(
                    f"{slot['workout_type']} workout — "
                    f"Target: {slot['target_duration']}min @ ~{slot['target_tss']:.0f} TSS. "
                    f"Phase: {week_data['phase']}. {week_data.get('week_instructions','')}"
                ),
                status="planned",
            ))
        db.commit()


def _get_feedback_history():
    with get_db() as db:
        fbs = db.query(WorkoutFeedback).filter(
            WorkoutFeedback.user_id == user_id
        ).order_by(WorkoutFeedback.created_at.desc()).limit(20).all()
        return [{"workout_type": f.workout_type, "difficulty": f.difficulty,
                 "rating": f.rating, "notes": f.notes} for f in fbs]


def _get_training_history():
    with get_db() as db:
        acts = db.query(Activity).filter(
            Activity.user_id == user_id
        ).order_by(Activity.start_date.desc()).limit(30).all()
        return [{"start_date": a.start_date.isoformat(), "tss": a.tss or 0} for a in acts]


# ═══════════════════════════════════════════════════════════════════════════════
# VIEW A — PROGRAM CREATION
# ═══════════════════════════════════════════════════════════════════════════════
def show_create_program_form():
    st.subheader("Create New Training Program")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Goal")
        goal_type = st.selectbox("Goal Type", ["Increase FTP", "Prepare for race", "Build base"])
        goal_description = st.text_area("Describe your goal", placeholder="e.g. I want to reach 300W FTP for my gran fondo in June")
        current_ftp = st.session_state.profile.get("ftp", 250)
        target_ftp = None
        if goal_type == "Increase FTP":
            target_ftp = st.number_input("Target FTP (W)", min_value=current_ftp, value=current_ftp + 30, step=5)
        min_date = datetime.now().date() + timedelta(weeks=4)
        max_date = datetime.now().date() + timedelta(weeks=24)
        target_date = st.date_input("Target Date", value=min_date + timedelta(weeks=8), min_value=min_date, max_value=max_date)

    with c2:
        st.markdown("### Volume")
        hours_per_week = st.slider("Hours/week", 4, 20, 10)
        sessions_per_week = st.slider("Sessions/week", 3, 7, 5)
        st.markdown("### Current Fitness")
        st.metric("FTP", f"{current_ftp}W")
        st.metric("CTL", f"{st.session_state.profile.get('ctl', 0):.0f}")
        st.metric("TSB", f"{st.session_state.profile.get('tsb', 0):.1f}")

    st.markdown("---")
    c1, c2, _ = st.columns([1, 1, 3])
    with c1:
        if st.button("Cancel"):
            st.session_state.program_view = "list"
            st.rerun()
    with c2:
        create_btn = st.button("Create Plan 🚀", type="primary")

    if create_btn:
        if not goal_description.strip():
            st.error("Please describe your goal")
            return

        total_weeks = (target_date - datetime.now().date()).days // 7

        with st.spinner(f"AI Coach designing your {total_weeks}-week program…"):
            try:
                user_input = (
                    f"Goal: {goal_description}. "
                    f"{'Target FTP: ' + str(target_ftp) + 'W. ' if target_ftp else ''}"
                    f"Target date: {target_date}. "
                    f"Available {hours_per_week}h/week, {sessions_per_week} sessions/week. "
                    f"Current FTP {current_ftp}W."
                )

                with get_db() as db:
                    acts = db.query(Activity).filter(Activity.user_id == user_id).order_by(
                        Activity.start_date.desc()).limit(30).all()
                    history = [{"start_date": a.start_date.isoformat(), "tss": a.tss or 0} for a in acts]
                    fbs = db.query(WorkoutFeedback).filter(WorkoutFeedback.user_id == user_id).all()
                    feedback_history = [{"workout_type": f.workout_type, "difficulty": f.difficulty} for f in fbs]

                agent = PlanAgent()
                result = agent.create_program(
                    user_input=user_input,
                    user_profile=st.session_state.profile,
                    training_history=history,
                    user_feedback_history=feedback_history,
                )

                macro_plan = result["macro_plan"]
                week_targets = macro_plan.get("week_targets", [])

                with get_db() as db:
                    program = TrainingProgram(
                        user_id=user_id,
                        name=macro_plan.get("program_name", f"{goal_type} Plan"),
                        goal_type=goal_type.lower().replace(" ", "_"),
                        goal_description=goal_description,
                        target_ftp=target_ftp,
                        target_date=datetime.combine(target_date, datetime.min.time()),
                        start_date=datetime.now(),
                        hours_per_week=hours_per_week,
                        sessions_per_week=sessions_per_week,
                        macro_plan_json=json.dumps(macro_plan),
                        initial_ftp=current_ftp,
                        initial_ctl=st.session_state.profile.get("ctl", 0),
                        status="active",
                    )
                    db.add(program)
                    db.flush()

                    week_plan_ids = []
                    for i, wt in enumerate(week_targets):
                        wk = wt.get("week", i + 1)
                        phase = wt.get("phase", "Base")
                        week_start = datetime.now() + timedelta(weeks=i)
                        wp = WeekPlan(
                            program_id=program.id,
                            week_number=wk,
                            phase=phase,
                            target_tss=wt.get("target_tss", hours_per_week * 50),
                            target_hours=wt.get("target_hours", hours_per_week),
                            target_sessions=sessions_per_week,
                            zone_focus=", ".join(wt.get("zone_focus", ["Endurance"])),
                            week_instructions=wt.get("week_instructions", ""),
                            status="current" if i == 0 else "upcoming",
                            start_date=week_start,
                            end_date=week_start + timedelta(days=6),
                        )
                        db.add(wp)
                        db.flush()
                        week_plan_ids.append((wp.id, dict(
                            week_number=wk, phase=phase,
                            target_tss=wt.get("target_tss", hours_per_week * 50),
                            zone_focus=", ".join(wt.get("zone_focus", ["Endurance"])),
                            week_instructions=wt.get("week_instructions", ""),
                        )))

                    db.commit()
                    program_id_new = program.id

                # Generate workout slots for ALL weeks (deterministic, fast)
                progress = st.progress(0)
                prog_data = {"sessions_per_week": sessions_per_week}
                for idx, (wp_id, wd) in enumerate(week_plan_ids):
                    progress.progress((idx + 1) / len(week_plan_ids))
                    _generate_workout_slots_for_week(wp_id, wd, prog_data)
                progress.empty()

                st.session_state.selected_program_id = program_id_new
                st.session_state.program_view = "plan_review"
                st.success("Program created! Review your plan below.")
                st.rerun()

            except Exception as e:
                st.error(f"Failed to create program: {e}")
                st.code(traceback.format_exc())


# ═══════════════════════════════════════════════════════════════════════════════
# VIEW B — PLAN REVIEW (validate all weeks before generating .zwo)
# ═══════════════════════════════════════════════════════════════════════════════
def show_plan_review(program_id: int):
    program_data, weeks_data = _load_common_data(program_id)
    if not program_data:
        st.error("Program not found")
        return

    c1, c2 = st.columns([4, 1])
    with c1:
        st.subheader(f"Review Plan: {program_data['name']}")
        st.caption("Approve each week or request changes. Once happy, generate all workouts.")
    with c2:
        if st.button("← Back"):
            st.session_state.program_view = "overview"
            st.rerun()

    # Count approved
    approved_weeks = [w for w in weeks_data if w["status"] in ("approved", "current")]
    total = len(weeks_data)
    st.progress(len(approved_weeks) / total if total else 0)
    st.caption(f"{len(approved_weeks)}/{total} weeks approved")

    # Bulk approve / generate buttons
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("✅ Approve All Weeks", use_container_width=True):
            with get_db() as db:
                db.query(WeekPlan).filter(WeekPlan.program_id == program_id).update(
                    {"status": "approved"}, synchronize_session=False
                )
                db.commit()
            st.rerun()
    with c2:
        if st.button("⚡ Generate All .zwo", type="primary", use_container_width=True):
            st.session_state[f"batch_generate_{program_id}"] = True
            st.rerun()
    with c3:
        if st.button("📅 View Calendar", use_container_width=True):
            st.session_state.program_view = "calendar"
            st.rerun()

    # Batch generation
    if st.session_state.get(f"batch_generate_{program_id}"):
        all_planned = [pw for w in weeks_data for pw in w["planned_workouts"] if pw["status"] == "planned"]
        if not all_planned:
            st.info("All workouts already generated or no planned workouts.")
            st.session_state.pop(f"batch_generate_{program_id}", None)
        else:
            with st.spinner(f"Generating {len(all_planned)} workouts…"):
                with get_db() as db:
                    planned_objs = db.query(PlannedWorkout).filter(
                        PlannedWorkout.id.in_([pw["id"] for pw in all_planned])
                    ).all()
                    history = _get_training_history()
                    feedback = _get_feedback_history()
                    results = batch_generate_week_workouts(
                        planned_workouts=planned_objs,
                        user_profile=st.session_state.profile,
                        training_history=history,
                        feedback_history=feedback,
                    )
                    for result, pw_obj in zip(results, planned_objs):
                        if result.get("workout_xml"):
                            structure = result.get("structure", {})
                            wp = WorkoutPlan(
                                user_id=user_id,
                                name=structure.get("NAME", pw_obj.workout_type),
                                workout_type=structure.get("TYPE", pw_obj.workout_type),
                                description=structure.get("RATIONALE", ""),
                                target_duration=int(safe_parse_number(structure.get("DURATION", pw_obj.target_duration), pw_obj.target_duration)),
                                target_tss=safe_parse_number(structure.get("TSS", pw_obj.target_tss), pw_obj.target_tss),
                                intensity_factor=safe_parse_number(structure.get("IF", 0), 0),
                                interval_structure=str(structure.get("intervals", "")),
                                zwo_xml=result["workout_xml"],
                                user_request=pw_obj.instructions,
                                agent_reasoning=result.get("reasoning", ""),
                            )
                            db.add(wp)
                            db.flush()
                            pw_obj.workout_plan_id = wp.id
                            pw_obj.status = "generated"
                    db.commit()
            st.success(f"Generated {len(all_planned)} workouts!")
            st.session_state.pop(f"batch_generate_{program_id}", None)
            st.rerun()

    st.markdown("---")

    # Week cards
    for week in weeks_data:
        wn = week["week_number"]
        phase = week["phase"]
        status = week["status"]
        status_color = {"approved": "🟢", "current": "🟡", "upcoming": "⚪", "completed": "✅"}.get(status, "⚪")

        with st.expander(
            f"{status_color} Week {wn} — {phase} phase | TSS {week['target_tss']:.0f} | {week['zone_focus']}",
            expanded=(wn == 1),
        ):
            if week["week_instructions"]:
                st.info(week["week_instructions"])

            # Workout slots
            pws = week["planned_workouts"]
            if pws:
                cols = st.columns(len(pws))
                for col, pw in zip(cols, pws):
                    color = _TYPE_COLOR.get(pw["workout_type"], "#aaa")
                    col.markdown(
                        f'<div style="background:{color}22;border-left:4px solid {color};'
                        f'padding:8px;border-radius:4px;margin-bottom:8px">'
                        f'<b>{pw["workout_type"]}</b><br>'
                        f'{pw["target_duration"]}min · TSS {pw["target_tss"]:.0f}</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No workout slots yet.")

            # Action buttons
            c1, c2, c3 = st.columns(3)
            with c1:
                if status != "approved" and st.button("✅ Approve Week", key=f"approve_{wn}"):
                    with get_db() as db:
                        db.query(WeekPlan).filter(
                            WeekPlan.program_id == program_id, WeekPlan.week_number == wn
                        ).update({"status": "approved"}, synchronize_session=False)
                        db.commit()
                    st.rerun()
            with c2:
                if st.button("✏️ Request Changes", key=f"change_{wn}"):
                    st.session_state[f"modify_week_{wn}"] = True

            with c3:
                if st.button("🔍 Week Detail", key=f"detail_{wn}"):
                    st.session_state.selected_week_number = wn
                    st.session_state.program_view = "week_detail"
                    st.rerun()

            # Modification dialog
            if st.session_state.get(f"modify_week_{wn}"):
                st.markdown("**What would you like to change?**")
                change_req = st.text_area(
                    "Describe changes",
                    key=f"change_text_{wn}",
                    placeholder="e.g. I'd prefer more VO2max sessions and less Endurance this week",
                )
                if st.button("Apply Changes", key=f"apply_change_{wn}"):
                    if change_req.strip():
                        with st.spinner("Re-planning week with your feedback…"):
                            try:
                                with get_db() as db:
                                    prog = db.query(TrainingProgram).filter(TrainingProgram.id == program_id).first()
                                    recent_wks = db.query(WeekPlan).filter(
                                        WeekPlan.program_id == program_id,
                                        WeekPlan.week_number < wn
                                    ).order_by(WeekPlan.week_number.desc()).limit(3).all()

                                    agent = PlanAgent()
                                    result = agent.plan_week(
                                        program=prog,
                                        week_number=wn,
                                        user_profile=st.session_state.profile,
                                        recent_weeks=recent_wks,
                                        user_override=change_req,
                                    )

                                    # Delete old slots and replace
                                    week_plan = db.query(WeekPlan).filter(
                                        WeekPlan.program_id == program_id, WeekPlan.week_number == wn
                                    ).first()
                                    db.query(PlannedWorkout).filter(
                                        PlannedWorkout.week_plan_id == week_plan.id,
                                        PlannedWorkout.status == "planned",
                                    ).delete(synchronize_session=False)
                                    db.commit()

                                for workout_spec in result["week_detail"].get("planned_workouts", []):
                                    with get_db() as db:
                                        week_plan = db.query(WeekPlan).filter(
                                            WeekPlan.program_id == program_id, WeekPlan.week_number == wn
                                        ).first()
                                        db.add(PlannedWorkout(
                                            week_plan_id=week_plan.id,
                                            day_index=workout_spec["day_index"],
                                            workout_type=workout_spec["workout_type"],
                                            target_tss=workout_spec["target_tss"],
                                            target_duration=workout_spec["target_duration"],
                                            instructions=workout_spec.get("instructions", ""),
                                            status="planned",
                                        ))
                                        db.commit()

                                st.success("Week updated!")
                                st.session_state.pop(f"modify_week_{wn}", None)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to re-plan week: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# VIEW C — PROGRAM OVERVIEW (macro, charts, calendar)
# ═══════════════════════════════════════════════════════════════════════════════
def show_program_overview(program_id: int):
    program_data, weeks_data = _load_common_data(program_id)
    if not program_data:
        st.error("Program not found")
        return

    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        st.subheader(program_data["name"])
        st.caption(program_data["goal_description"])
    with c2:
        if st.button("📋 Review Plan", type="primary", use_container_width=True):
            st.session_state.program_view = "plan_review"
            st.rerun()
    with c3:
        if st.button("← Programs", use_container_width=True):
            st.session_state.program_view = "list"
            st.rerun()

    st.markdown("---")

    # Progress metrics
    completed = len([w for w in weeks_data if w["status"] == "completed"])
    total = len(weeks_data)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Weeks", f"{completed}/{total}")
    current_ftp = st.session_state.profile.get("ftp", 0)
    if program_data.get("target_ftp"):
        c2.metric("FTP", f"{current_ftp}W → {program_data['target_ftp']:.0f}W",
                  delta=f"+{current_ftp - program_data['initial_ftp']:.0f}W")
    else:
        c2.metric("FTP", f"{current_ftp}W")
    days_left = (program_data["target_date"] - datetime.now()).days
    c3.metric("Days Left", days_left)
    c4.metric("CTL", f"{st.session_state.profile.get('ctl', 0):.0f}",
              delta=f"+{st.session_state.profile.get('ctl', 0) - program_data['initial_ctl']:.0f}")
    st.progress(completed / total if total else 0)

    # Phase timeline
    st.markdown("---")
    macro_plan = json.loads(program_data["macro_plan_json"])
    try:
        st.plotly_chart(create_program_timeline(macro_plan), use_container_width=True)
    except Exception:
        pass

    # TSS planned vs actual + CTL progression
    c1, c2 = st.columns(2)
    class _Week:
        def __init__(self, d):
            self.week_number = d["week_number"]
            self.target_tss = d["target_tss"]
            self.actual_tss = d["actual_tss"]
            self.actual_ctl = d.get("actual_ctl")
            self.phase = d["phase"]
    mock_weeks = [_Week(w) for w in weeks_data]
    class _Prog:
        def __init__(self, d):
            self.initial_ctl = d["initial_ctl"]
            self.macro_plan_json = d["macro_plan_json"]
    with c1:
        try:
            st.plotly_chart(create_planned_vs_actual_tss(mock_weeks), use_container_width=True)
        except Exception:
            pass
    with c2:
        try:
            st.plotly_chart(create_program_progress_chart(_Prog(program_data), mock_weeks), use_container_width=True)
        except Exception:
            pass

    # ── Re-evaluate button ─────────────────────────────────────────────────
    st.markdown("---")
    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        if st.button("🔄 Re-evaluate Plan (from Strava actuals)", use_container_width=True):
            st.session_state[f"reevaluate_{program_id}"] = True

    with c2:
        if st.button("📅 Calendar View", use_container_width=True):
            st.session_state.program_view = "calendar"
            st.rerun()

    with c3:
        # TrainingPeaks sync
        if _TP_AVAILABLE:
            from config import settings as cfg
            if cfg.trainingpeaks_client_id:
                if st.button("🔗 Sync to TrainingPeaks", use_container_width=True):
                    st.session_state[f"tp_sync_{program_id}"] = True
            else:
                st.caption("Add TRAININGPEAKS_CLIENT_ID to .env to enable TP sync")

    # Re-evaluation UI
    if st.session_state.get(f"reevaluate_{program_id}"):
        _show_reevaluation(program_id, program_data, weeks_data)

    # TrainingPeaks sync UI
    if st.session_state.get(f"tp_sync_{program_id}") and _TP_AVAILABLE:
        _show_tp_sync(program_id, program_data, weeks_data)

    # Current week
    st.markdown("---")
    st.subheader("Current Week")
    current_week = next((w for w in weeks_data if w["status"] == "current"),
                        weeks_data[0] if weeks_data else None)
    if current_week:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Week", current_week["week_number"])
        c2.metric("Phase", current_week["phase"])
        c3.metric("Target TSS", f"{current_week['target_tss']:.0f}")
        with c4:
            if st.button("View Week Details →", type="primary", use_container_width=True):
                st.session_state.selected_week_number = current_week["week_number"]
                st.session_state.program_view = "week_detail"
                st.rerun()


def _show_reevaluation(program_id, program_data, weeks_data):
    st.markdown("### Re-evaluation")
    engine = AdaptationEngine()
    profile = st.session_state.profile

    # Find completed + current weeks
    recent_completed = [w for w in weeks_data if w["status"] == "completed"][-3:]

    class _WeekMock:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, v)
    recent_mocks = [_WeekMock(w) for w in recent_completed]

    adjustments = engine.calculate_adjustments(
        program=None,
        current_week_number=len([w for w in weeks_data if w["status"] == "completed"]) + 1,
        current_profile=profile,
        recent_weeks=recent_mocks,
    )
    risk = engine.detect_overtraining_risk(profile, recent_mocks)

    st.markdown(f"**Overtraining Risk:** `{risk['risk_level'].upper()}`")
    if risk["warnings"]:
        for w in risk["warnings"]:
            st.warning(w)

    multiplier = adjustments["tss_multiplier"]
    st.markdown(f"**Recommended TSS adjustment:** ×{multiplier:.2f}")
    for r in adjustments["reasons"]:
        st.info(r)

    if adjustments["force_recovery"]:
        st.error("Recovery week recommended immediately.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Apply Adjustments to Future Weeks", type="primary"):
            with get_db() as db:
                upcoming = db.query(WeekPlan).filter(
                    WeekPlan.program_id == program_id,
                    WeekPlan.status.in_(["upcoming", "approved"]),
                ).all()
                for wk in upcoming:
                    wk.target_tss = round(wk.target_tss * multiplier, 1)
                    wk.adaptation_notes = "; ".join(adjustments["reasons"])
                db.commit()
            st.success(f"Updated {len(upcoming)} upcoming weeks.")
            st.session_state.pop(f"reevaluate_{program_id}", None)
            st.rerun()
    with c2:
        if st.button("Dismiss"):
            st.session_state.pop(f"reevaluate_{program_id}", None)
            st.rerun()


def _show_tp_sync(program_id, program_data, weeks_data):
    st.markdown("### TrainingPeaks Sync")
    if "tp_token" not in st.session_state:
        from src.trainingpeaks.client import TrainingPeaksClient
        auth_url = TrainingPeaksClient.get_authorization_url()
        st.markdown(
            f'<a href="{auth_url}" target="_blank">'
            f'<button style="background:#2193b0;color:white;padding:10px 24px;border:none;border-radius:4px;cursor:pointer">'
            f'Connect TrainingPeaks</button></a>',
            unsafe_allow_html=True,
        )
        code = st.text_input("Paste TP auth code here:")
        if code:
            try:
                from src.trainingpeaks.client import TrainingPeaksClient
                tokens = TrainingPeaksClient.exchange_code_for_token(code)
                st.session_state.tp_token = tokens["access_token"]
                st.session_state.tp_athlete_id = tokens.get("athlete_id")
                st.success("TrainingPeaks connected!")
                st.rerun()
            except Exception as e:
                st.error(f"TP auth error: {e}")
    else:
        from src.trainingpeaks.client import TrainingPeaksClient
        client = TrainingPeaksClient(st.session_state.tp_token)
        athlete_id = st.session_state.get("tp_athlete_id")

        if st.button("Upload all planned workouts to TrainingPeaks"):
            all_pw = [pw for w in weeks_data for pw in w["planned_workouts"]]
            # Enrich with zwo if generated
            enriched = []
            for pw in all_pw:
                entry = dict(pw)
                if pw["workout_plan_id"]:
                    with get_db() as db:
                        wp = db.query(WorkoutPlan).filter(WorkoutPlan.id == pw["workout_plan_id"]).first()
                        if wp:
                            entry["name"] = wp.name
                            entry["zwo_xml"] = wp.zwo_xml
                enriched.append(entry)

            with st.spinner("Uploading to TrainingPeaks…"):
                summary = client.sync_program_to_trainingpeaks(
                    athlete_id=athlete_id,
                    planned_workouts=enriched,
                    program_start_date=program_data["start_date"],
                )
            st.success(f"Uploaded {summary['uploaded']} workouts.")
            if summary["failed"]:
                st.warning(f"{summary['failed']} failed: {summary['errors'][:3]}")
            st.session_state.pop(f"tp_sync_{program_id}", None)
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# VIEW D — CALENDAR
# ═══════════════════════════════════════════════════════════════════════════════
def show_calendar(program_id: int):
    program_data, weeks_data = _load_common_data(program_id)
    if not program_data:
        st.error("Program not found")
        return

    c1, c2 = st.columns([4, 1])
    with c1:
        st.subheader(f"Calendar — {program_data['name']}")
    with c2:
        if st.button("← Overview"):
            st.session_state.program_view = "overview"
            st.rerun()

    # Legend
    legend_cols = st.columns(len(_TYPE_COLOR))
    for col, (wtype, color) in zip(legend_cols, _TYPE_COLOR.items()):
        col.markdown(
            f'<span style="background:{color};padding:2px 8px;border-radius:3px;'
            f'color:white;font-size:12px">{wtype}</span>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Header row
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    header = st.columns([1] + [2] * 7)
    header[0].markdown("**Week**")
    for i, d in enumerate(day_names):
        header[i + 1].markdown(f"**{d}**")

    for week in weeks_data:
        # Map day_index → workout
        day_map = {pw["day_index"]: pw for pw in week["planned_workouts"]}
        cols = st.columns([1] + [2] * 7)

        with cols[0]:
            status_icon = {"approved": "🟢", "current": "🟡", "completed": "✅", "upcoming": "⚪"}.get(week["status"], "⚪")
            st.markdown(f"{status_icon} **W{week['week_number']}**")
            st.caption(week["phase"])

        for day in range(1, 8):
            with cols[day]:
                pw = day_map.get(day)
                if pw:
                    color = _TYPE_COLOR.get(pw["workout_type"], "#aaa")
                    check = "✅" if pw["status"] == "generated" else "📋"
                    st.markdown(
                        f'<div style="background:{color}33;border:1px solid {color};'
                        f'border-radius:4px;padding:4px 6px;font-size:11px;cursor:pointer">'
                        f'{check} <b>{pw["workout_type"][:6]}</b><br>'
                        f'{pw["target_duration"]}min · {pw["target_tss"]:.0f}TSS</div>',
                        unsafe_allow_html=True,
                    )
                    if st.button("→", key=f"cal_open_{pw['id']}", use_container_width=True):
                        st.session_state.selected_week_number = week["week_number"]
                        st.session_state.program_view = "week_detail"
                        st.rerun()
                else:
                    st.markdown('<div style="color:#ccc;font-size:11px;padding:4px">—</div>',
                                unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# VIEW E — WEEK DETAIL
# ═══════════════════════════════════════════════════════════════════════════════
def show_week_detail(program_id: int, week_number: int):
    with get_db() as db:
        program = db.query(TrainingProgram).filter(TrainingProgram.id == program_id).first()
        week_plan = db.query(WeekPlan).filter(
            WeekPlan.program_id == program_id, WeekPlan.week_number == week_number
        ).first()
        if not week_plan:
            # Week number out of range — reset to overview
            st.session_state.selected_week_number = 1
            st.session_state.program_view = "overview"
            st.rerun()
            return

        program_data = {
            "id": program.id, "name": program.name,
            "sessions_per_week": program.sessions_per_week,
        }
        week_data = {
            "id": week_plan.id, "week_number": week_plan.week_number,
            "phase": week_plan.phase, "target_tss": week_plan.target_tss,
            "zone_focus": week_plan.zone_focus or "",
            "week_instructions": week_plan.week_instructions or "",
            "adaptation_notes": week_plan.adaptation_notes or "",
            "actual_tss": week_plan.actual_tss, "status": week_plan.status,
        }
        planned_workouts = db.query(PlannedWorkout).filter(
            PlannedWorkout.week_plan_id == week_plan.id
        ).order_by(PlannedWorkout.day_index).all()
        workouts_data = [{
            "id": pw.id, "day_index": pw.day_index,
            "workout_type": pw.workout_type, "target_tss": pw.target_tss,
            "target_duration": pw.target_duration,
            "instructions": pw.instructions or "",
            "status": pw.status, "workout_plan_id": pw.workout_plan_id,
        } for pw in planned_workouts]

    # Header
    c1, c2, c3 = st.columns([3, 1, 1])
    with c1:
        st.subheader(f"Week {week_data['week_number']} — {week_data['phase']} Phase")
    with c2:
        if st.button("📋 Plan Review"):
            st.session_state.program_view = "plan_review"
            st.rerun()
    with c3:
        if st.button("← Overview"):
            st.session_state.program_view = "overview"
            st.rerun()

    # Week summary
    c1, c2, c3 = st.columns(3)
    c1.metric("Target TSS", f"{week_data['target_tss']:.0f}")
    c2.metric("Zone Focus", week_data["zone_focus"].replace(",", ", "))
    if week_data["actual_tss"]:
        c3.metric("Actual TSS", f"{week_data['actual_tss']:.0f}",
                  delta=f"{week_data['actual_tss'] - week_data['target_tss']:.0f}")

    if week_data["week_instructions"]:
        st.info(week_data["week_instructions"])
    if week_data["adaptation_notes"]:
        st.warning(f"Adaptations: {week_data['adaptation_notes']}")

    # Nav between weeks — check bounds using loaded data
    with get_db() as db:
        max_week = db.query(WeekPlan).filter(
            WeekPlan.program_id == program_id
        ).order_by(WeekPlan.week_number.desc()).first()
        max_week_number = max_week.week_number if max_week else week_number

    c1, c2, c3 = st.columns([1, 3, 1])
    with c1:
        if week_number > 1 and st.button("← Prev Week"):
            st.session_state.selected_week_number = week_number - 1
            st.rerun()
    with c3:
        if week_number < max_week_number and st.button("Next Week →"):
            st.session_state.selected_week_number = week_number + 1
            st.rerun()

    # Generate slots if missing
    if not workouts_data:
        st.warning("No workouts planned for this week.")
        if st.button("Plan Workouts (AI)", type="primary"):
            with st.spinner("Planning…"):
                try:
                    with get_db() as db:
                        prog = db.query(TrainingProgram).filter(TrainingProgram.id == program_id).first()
                        recent = db.query(WeekPlan).filter(
                            WeekPlan.program_id == program_id,
                            WeekPlan.week_number < week_number
                        ).order_by(WeekPlan.week_number.desc()).limit(3).all()
                        agent = PlanAgent()
                        result = agent.plan_week(
                            program=prog, week_number=week_number,
                            user_profile=st.session_state.profile, recent_weeks=recent,
                        )
                        wk = db.query(WeekPlan).filter(
                            WeekPlan.program_id == program_id, WeekPlan.week_number == week_number
                        ).first()
                        for spec in result["week_detail"].get("planned_workouts", []):
                            db.add(PlannedWorkout(
                                week_plan_id=wk.id,
                                day_index=spec["day_index"],
                                workout_type=spec["workout_type"],
                                target_tss=spec["target_tss"],
                                target_duration=spec["target_duration"],
                                instructions=spec.get("instructions", ""),
                                status="planned",
                            ))
                        db.commit()
                    st.success("Workouts planned!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")
        return

    st.markdown("---")
    st.subheader(f"Workouts ({len(workouts_data)} sessions)")

    for workout in workouts_data:
        _render_workout_card(workout, program_id, week_number, program_data, week_data)

    # Mark week as skipped / re-plan
    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("⏭️ Skip Week (mark all skipped)", use_container_width=True):
            with get_db() as db:
                db.query(PlannedWorkout).filter(
                    PlannedWorkout.week_plan_id == week_data["id"],
                    PlannedWorkout.status == "planned",
                ).update({"status": "skipped"}, synchronize_session=False)
                db.query(WeekPlan).filter(WeekPlan.id == week_data["id"]).update(
                    {"status": "skipped"}, synchronize_session=False
                )
                db.commit()
            st.rerun()
    with c2:
        if st.button("🔄 Re-plan This Week (adaptive)", use_container_width=True):
            st.session_state[f"replan_week_{week_number}"] = True

    if st.session_state.get(f"replan_week_{week_number}"):
        with st.spinner("Re-planning week with AdaptationEngine…"):
            try:
                engine = AdaptationEngine()
                with get_db() as db:
                    prog = db.query(TrainingProgram).filter(TrainingProgram.id == program_id).first()
                    recent_wks = db.query(WeekPlan).filter(
                        WeekPlan.program_id == program_id, WeekPlan.week_number < week_number
                    ).order_by(WeekPlan.week_number.desc()).limit(3).all()
                    adjustments = engine.calculate_adjustments(
                        program=prog, current_week_number=week_number,
                        current_profile=st.session_state.profile, recent_weeks=recent_wks,
                    )
                    wk = db.query(WeekPlan).filter(
                        WeekPlan.program_id == program_id, WeekPlan.week_number == week_number
                    ).first()
                    new_tss = round(wk.target_tss * adjustments["tss_multiplier"], 1)
                    wk.target_tss = new_tss
                    wk.adaptation_notes = "; ".join(adjustments["reasons"])
                    # Replace planned slots
                    db.query(PlannedWorkout).filter(
                        PlannedWorkout.week_plan_id == wk.id, PlannedWorkout.status == "planned"
                    ).delete(synchronize_session=False)
                    db.commit()
                    zone_focus = [z.strip() for z in (wk.zone_focus or "Endurance").split(",")]
                    slots = engine.adjust_week_distribution(
                        target_tss=new_tss,
                        sessions_per_week=prog.sessions_per_week,
                        zone_focus=zone_focus,
                        current_profile=st.session_state.profile,
                    )
                    for slot in slots:
                        db.add(PlannedWorkout(
                            week_plan_id=wk.id,
                            day_index=slot["day_index"],
                            workout_type=slot["workout_type"],
                            target_tss=slot["target_tss"],
                            target_duration=slot["target_duration"],
                            instructions=f"{slot['workout_type']} · {slot['target_duration']}min · TSS {slot['target_tss']:.0f}",
                            status="planned",
                        ))
                    db.commit()

                for r in adjustments["reasons"]:
                    st.info(r)
                st.success(f"Re-planned! New TSS target: {new_tss:.0f}")
                st.session_state.pop(f"replan_week_{week_number}", None)
                st.rerun()
            except Exception as e:
                st.error(f"Re-plan failed: {e}")


def _render_workout_card(workout, program_id, week_number, program_data, week_data):
    """Render a single workout card with generate / alternative / details."""
    wid = workout["id"]
    status = workout["status"]
    status_icon = {"planned": "📋", "generated": "✅", "completed": "🏆", "skipped": "⏭️"}.get(status, "")

    with st.container():
        color = _TYPE_COLOR.get(workout["workout_type"], "#888")
        c1, c2, c3, c4 = st.columns([3, 1, 1, 3])
        with c1:
            st.markdown(
                f'<div style="border-left:4px solid {color};padding-left:8px">'
                f'<b>{status_icon} Workout {workout["day_index"]}: {workout["workout_type"]}</b></div>',
                unsafe_allow_html=True,
            )
        c2.metric("TSS", f"~{workout['target_tss']:.0f}")
        c3.metric("Duration", f"{workout['target_duration']}min")

        with c4:
            btn_cols = st.columns(3)
            if status == "planned":
                if btn_cols[0].button("Generate .zwo", key=f"gen_{wid}", use_container_width=True):
                    st.session_state[f"generating_{wid}"] = True
                    st.rerun()
                if btn_cols[1].button("Alternative", key=f"alt_{wid}", use_container_width=True):
                    st.session_state[f"gen_alt_{wid}"] = True
                    st.rerun()
            elif status == "generated":
                if btn_cols[0].button("Details", key=f"view_{wid}", use_container_width=True):
                    k = f"show_details_{wid}"
                    st.session_state[k] = not st.session_state.get(k, False)
                    st.rerun()
                if btn_cols[1].button("Alternative", key=f"alt_{wid}", use_container_width=True):
                    st.session_state[f"gen_alt_{wid}"] = True
                    st.rerun()

        # ── Generate .zwo ──────────────────────────────────────────────────
        if st.session_state.get(f"generating_{wid}"):
            _do_generate_workout(wid, workout, week_data)

        # ── Generate Alternative ───────────────────────────────────────────
        if st.session_state.get(f"gen_alt_{wid}"):
            _do_generate_alternative(wid, workout, week_data)

        # ── Workout details ────────────────────────────────────────────────
        if status == "generated" and st.session_state.get(f"show_details_{wid}"):
            _render_workout_details(wid, workout)

        st.markdown("---")


def _do_generate_workout(wid, workout, week_data, is_alternative=False):
    label = "alternative" if is_alternative else "workout"
    with st.spinner(f"Generating {label}…"):
        try:
            with get_db() as db:
                pw_obj = db.query(PlannedWorkout).filter(PlannedWorkout.id == wid).first()
                if is_alternative:
                    pw_obj.instructions = (pw_obj.instructions or "") + " [ALTERNATIVE: propose a different interval structure with same energy system but different format]"
                history = _get_training_history()
                feedback = _get_feedback_history()
                result = generate_planned_workout(
                    planned_workout=pw_obj,
                    user_profile=st.session_state.profile,
                    training_history=history,
                    feedback_history=feedback,
                )
                if result.get("workout_xml"):
                    structure = result.get("structure", {})
                    wp = WorkoutPlan(
                        user_id=user_id,
                        name=("ALT: " if is_alternative else "") + structure.get("NAME", workout["workout_type"]),
                        workout_type=structure.get("TYPE", workout["workout_type"]),
                        description=structure.get("RATIONALE", ""),
                        target_duration=int(safe_parse_number(structure.get("DURATION", workout["target_duration"]), workout["target_duration"])),
                        target_tss=safe_parse_number(structure.get("TSS", workout["target_tss"]), workout["target_tss"]),
                        intensity_factor=safe_parse_number(structure.get("IF", 0), 0),
                        interval_structure=str(structure.get("intervals", "")),
                        zwo_xml=result["workout_xml"],
                        user_request=pw_obj.instructions,
                        agent_reasoning=result.get("reasoning", ""),
                    )
                    db.add(wp)
                    db.flush()
                    pw_obj.workout_plan_id = wp.id
                    pw_obj.status = "generated"
                    db.commit()
                    st.success(f"{'Alternative' if is_alternative else 'Workout'} generated!")
                    st.session_state.pop(f"generating_{wid}", None)
                    st.session_state.pop(f"gen_alt_{wid}", None)
                    st.session_state[f"show_details_{wid}"] = True
                    st.rerun()
                else:
                    st.error("Generation failed — no XML produced.")
                    st.session_state.pop(f"generating_{wid}", None)
                    st.session_state.pop(f"gen_alt_{wid}", None)
        except Exception as e:
            st.error(f"Error: {e}")
            st.session_state.pop(f"generating_{wid}", None)
            st.session_state.pop(f"gen_alt_{wid}", None)


def _do_generate_alternative(wid, workout, week_data):
    _do_generate_workout(wid, workout, week_data, is_alternative=True)


def _render_workout_details(wid, workout):
    with get_db() as db:
        wp = db.query(WorkoutPlan).filter(WorkoutPlan.id == workout["workout_plan_id"]).first()
        if not wp:
            return
        name = wp.name
        wtype = wp.workout_type
        tss = wp.target_tss
        if_ = wp.intensity_factor
        desc = wp.description
        interval_structure = wp.interval_structure
        zwo_xml = wp.zwo_xml
        reasoning = wp.agent_reasoning

    st.markdown("---")
    st.markdown(f"### {name}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Type", wtype or "N/A")
    c2.metric("TSS", f"{tss:.0f}" if tss else "N/A")
    c3.metric("IF", f"{if_:.2f}" if if_ else "N/A")

    if desc:
        st.info(desc)

    # Interval chart
    if zwo_xml:
        try:
            from src.agent.workout_agent import WorkoutAgent as _WA
            intervals = _WA()._parse_intervals(interval_structure)
            ftp = st.session_state.profile.get("ftp", 250)
            st.plotly_chart(create_workout_profile_chart(intervals, ftp), use_container_width=True)
        except Exception:
            pass

    with st.expander("Workout Structure"):
        st.code(interval_structure or "N/A")

    # Download
    c1, c2 = st.columns([2, 1])
    with c1:
        filename = f"{name.replace(' ', '_')}.zwo"
        st.download_button("⬇️ Download .zwo", data=zwo_xml, file_name=filename,
                           mime="application/xml", key=f"dl_{wid}", use_container_width=True)
    with c2:
        if st.button("Close", key=f"close_details_{wid}", use_container_width=True):
            st.session_state[f"show_details_{wid}"] = False
            st.rerun()

    with st.expander("Preview XML"):
        st.code(zwo_xml, language="xml")
    if reasoning:
        with st.expander("AI Reasoning"):
            st.text(reasoning)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ROUTER
# ═══════════════════════════════════════════════════════════════════════════════
with get_db() as db:
    programs_list = [{
        "id": p.id, "name": p.name,
        "target_date": p.target_date, "status": p.status,
    } for p in db.query(TrainingProgram).filter(
        TrainingProgram.user_id == user_id,
        TrainingProgram.status.in_(["active", "paused"])
    ).all()]

view = st.session_state.program_view

if view == "create":
    show_create_program_form()

elif view == "plan_review":
    if st.session_state.selected_program_id:
        show_plan_review(st.session_state.selected_program_id)
    else:
        st.session_state.program_view = "list"
        st.rerun()

elif view == "overview":
    if st.session_state.selected_program_id:
        show_program_overview(st.session_state.selected_program_id)
    else:
        st.session_state.program_view = "list"
        st.rerun()

elif view == "calendar":
    if st.session_state.selected_program_id:
        show_calendar(st.session_state.selected_program_id)
    else:
        st.session_state.program_view = "list"
        st.rerun()

elif view == "week_detail":
    if st.session_state.selected_program_id:
        show_week_detail(st.session_state.selected_program_id, st.session_state.selected_week_number)
    else:
        st.session_state.program_view = "list"
        st.rerun()

else:  # list
    if not programs_list:
        st.info("No training programs yet.")
        if st.button("Create Training Program", type="primary"):
            st.session_state.program_view = "create"
            st.rerun()
    else:
        st.subheader("Your Training Programs")
        for prog in programs_list:
            with st.container():
                c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
                c1.markdown(f"### {prog['name']}")
                c1.caption(f"Target: {prog['target_date'].strftime('%B %d, %Y')}")
                c2.metric("Status", prog["status"].upper())
                with c3:
                    if st.button("View", key=f"view_{prog['id']}", use_container_width=True):
                        st.session_state.selected_program_id = prog["id"]
                        st.session_state.program_view = "overview"
                        st.rerun()
                with c4:
                    if st.button("Review", key=f"review_{prog['id']}", use_container_width=True):
                        st.session_state.selected_program_id = prog["id"]
                        st.session_state.program_view = "plan_review"
                        st.rerun()
                st.markdown("---")

        if st.button("+ Create New Program", type="primary"):
            st.session_state.program_view = "create"
            st.rerun()
