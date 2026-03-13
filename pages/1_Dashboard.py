"""
Dashboard — Training overview + Strava sync (merged from Analytics)
"""
import re
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.database import get_db
from src.database.models import User, Activity, UserProfile
from src.strava.auth import StravaAuth
from src.strava.client import StravaDataClient
from src.strava.data_processor import StravaDataProcessor
from src.strava.metrics import TrainingMetrics
from src.strava.power_profile import PowerProfileAnalyzer
from src.strava.power_curve_calculator import (
    calculate_best_efforts_from_activities,
    update_power_curve_with_pr_tracking,
)
from src.visualization.charts import (
    create_pmc_chart,
    create_weekly_tss_chart,
    create_zone_distribution_chart,
    create_power_curve_spider_chart,
)

st.set_page_config(page_title="Dashboard", page_icon="🏠", layout="wide")
st.title("🏠 Dashboard")

if st.session_state.pop("just_connected", False):
    st.success(f"✅ Strava connected! Welcome, {st.session_state.get('user', {}).get('name', '')} — now set your FTP in **Settings** then sync your activities.")

# Multi-user: session identifies the user — no auto-load from DB

# ── Handle OAuth callback BEFORE tabs (st.stop() in tabs would block this) ────
_auth = StravaAuth()
_query_params = st.query_params
_auth_code = _query_params.get("code")
if _auth_code and not st.session_state.get("processing_auth") and "user" not in st.session_state:
    st.session_state.processing_auth = True
    try:
        tokens = _auth.exchange_code_for_token(_auth_code)
        with get_db() as _db:
            from src.database.models import User as _User
            _strava_id = tokens.get("strava_id")
            _user = _db.query(_User).filter(_User.strava_id == _strava_id).first() if _strava_id else None
            if _user:
                _user.strava_access_token = tokens["access_token"]
                _user.strava_refresh_token = tokens["refresh_token"]
                _user.strava_token_expires_at = tokens["expires_at"]
                if tokens.get("athlete_name"):
                    _user.name = tokens["athlete_name"]
                _db.commit()
            else:
                _user = _User(
                    strava_id=_strava_id,
                    name=tokens.get("athlete_name", "Cyclist"),
                    strava_access_token=tokens["access_token"],
                    strava_refresh_token=tokens["refresh_token"],
                    strava_token_expires_at=tokens["expires_at"],
                )
                _db.add(_user)
                _db.commit()
            st.session_state.user = {"id": _user.id, "name": _user.name}
            st.session_state.strava_connected = True
            st.session_state.just_connected = True
        st.query_params.clear()
        st.session_state.pop("processing_auth", None)
        st.rerun()
    except Exception as _e:
        st.error(f"Error connecting to Strava: {_e}")
        st.session_state.pop("processing_auth", None)
        st.query_params.clear()


def _get_or_create_user(tokens, db):
    strava_id = tokens.get("strava_id")
    user = None
    if strava_id:
        user = db.query(User).filter(User.strava_id == strava_id).first()
    if user:
        user.strava_access_token = tokens["access_token"]
        user.strava_refresh_token = tokens["refresh_token"]
        user.strava_token_expires_at = tokens["expires_at"]
        if tokens.get("athlete_name"):
            user.name = tokens["athlete_name"]
        db.commit()
        return user
    user = User(
        strava_id=strava_id,
        name=tokens.get("athlete_name", "Cyclist"),
        strava_access_token=tokens["access_token"],
        strava_refresh_token=tokens["refresh_token"],
        strava_token_expires_at=tokens["expires_at"],
    )
    db.add(user)
    db.commit()
    return user


def _ensure_valid_token(user, db):
    if user.strava_token_expires_at and user.strava_token_expires_at < datetime.utcnow() + timedelta(minutes=5):
        auth = StravaAuth()
        new_tokens = auth.refresh_access_token(user.strava_refresh_token)
        user.strava_access_token = new_tokens["access_token"]
        user.strava_refresh_token = new_tokens["refresh_token"]
        user.strava_token_expires_at = new_tokens["expires_at"]
        db.commit()
        return new_tokens["access_token"]
    return user.strava_access_token


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_overview, tab_sync = st.tabs(["📊 Overview", "🔄 Strava Sync"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════════
with tab_overview:
    if "user" not in st.session_state:
        st.info("Connect your Strava account in the **Strava Sync** tab to see your metrics.")
        st.stop()

    with get_db() as db:
        profile_db = db.query(UserProfile).filter(
            UserProfile.user_id == st.session_state.user["id"]
        ).first()

        if not profile_db:
            st.warning("Set your FTP in Settings and sync activities from the Strava Sync tab.")
            st.stop()

        ftp = profile_db.ftp
        ctl = profile_db.ctl or 0
        atl = profile_db.atl or 0
        tsb = profile_db.tsb or 0

        recent_7d_db = db.query(Activity).filter(
            Activity.user_id == st.session_state.user["id"],
            Activity.start_date >= datetime.now() - timedelta(days=7),
        ).all()
        recent_7d = [
            {"start_date": a.start_date, "name": a.name, "duration": a.duration,
             "tss": a.tss, "normalized_power": a.normalized_power}
            for a in recent_7d_db
        ]

        recent_90d_db = db.query(Activity).filter(
            Activity.user_id == st.session_state.user["id"],
            Activity.start_date >= datetime.now() - timedelta(days=90),
        ).order_by(Activity.start_date).all()
        recent_90d = [
            {"start_date": a.start_date, "tss": a.tss or 0,
             "time_zone1": a.time_zone1, "time_zone2": a.time_zone2,
             "time_zone3": a.time_zone3, "time_zone4": a.time_zone4,
             "time_zone5": a.time_zone5, "time_zone6": a.time_zone6,
             "time_zone7": a.time_zone7}
            for a in recent_90d_db
        ]

        power_profile_data = None
        if profile_db.best_5s:
            power_curve = {k: v for k, v in {
                "5s": profile_db.best_5s, "15s": profile_db.best_15s,
                "30s": profile_db.best_30s, "1min": profile_db.best_1min,
                "5min": profile_db.best_5min, "20min": profile_db.best_20min,
                "60min": profile_db.best_60min,
            }.items() if v is not None}
            analyzer = PowerProfileAnalyzer(ftp=ftp, weight=profile_db.weight or 75.0)
            power_profile_data = analyzer.analyze_from_best_efforts(power_curve)
            power_profile_data["power_curve"] = power_curve
            power_profile_data["rider_type"] = profile_db.rider_type

    # ── Fitness metrics row ───────────────────────────────────────────────────
    tss_7d = sum(a["tss"] or 0 for a in recent_7d)
    tsb_emoji = "🟢" if tsb > 5 else "🟡" if tsb > -10 else "🔴"

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("FTP", f"{ftp:.0f} W")
    c2.metric("CTL — Fitness", f"{ctl:.1f}")
    c3.metric("ATL — Fatigue", f"{atl:.1f}")
    c4.metric(f"TSB — Form  {tsb_emoji}", f"{tsb:.1f}")
    c5.metric("7-Day TSS", f"{tss_7d:.0f}")

    if tsb > 5:
        st.success("Fresh — ready for hard training.")
    elif tsb > -10:
        st.info("Optimal training zone — good balance.")
    else:
        st.warning("Fatigued — consider a recovery or easy endurance day.")

    st.markdown("---")

    # ── Charts ────────────────────────────────────────────────────────────────
    if len(recent_90d) >= 5:
        st.subheader("Performance Management Chart")
        st.plotly_chart(create_pmc_chart(recent_90d), use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(create_weekly_tss_chart(recent_90d), use_container_width=True)
        with c2:
            st.plotly_chart(create_zone_distribution_chart(recent_90d), use_container_width=True)

        # Power profile
        if power_profile_data:
            st.markdown("---")
            st.subheader("Power Profile")
            c1, c2 = st.columns([2, 1])
            with c1:
                spider_fig = create_power_curve_spider_chart(
                    power_curve=power_profile_data["power_curve"],
                    percentiles=power_profile_data["percentiles"],
                    rider_type=power_profile_data["rider_type"],
                )
                st.plotly_chart(spider_fig, use_container_width=True)
            with c2:
                st.markdown(f"**Rider Type:** {power_profile_data['rider_type'].replace('_', ' ').title() if power_profile_data['rider_type'] else 'Unknown'}")
                if power_profile_data.get("strengths"):
                    st.success(f"**Strengths:** {', '.join(power_profile_data['strengths'])}")
                if power_profile_data.get("weaknesses"):
                    st.warning(f"**Weaknesses:** {', '.join(power_profile_data['weaknesses'])}")
                if power_profile_data.get("recommendations"):
                    st.info(power_profile_data["recommendations"])

        st.markdown("---")
        st.subheader("Last 7 Days")
        if recent_7d:
            rows = [
                {"Date": a["start_date"].strftime("%a %d %b"), "Name": a["name"],
                 "Duration": f"{(a['duration'] or 0) // 60}min",
                 "TSS": round(a["tss"], 1) if a["tss"] else "N/A",
                 "NP": round(a["normalized_power"], 0) if a["normalized_power"] else "N/A"}
                for a in sorted(recent_7d, key=lambda x: x["start_date"], reverse=True)
            ]
            st.dataframe(rows, use_container_width=True)
        else:
            st.caption("No activities in the last 7 days.")
    else:
        st.info("Sync activities in the **Strava Sync** tab to see charts (need at least 5 activities).")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — STRAVA SYNC
# ═══════════════════════════════════════════════════════════════════════════════
with tab_sync:
    auth = StravaAuth()

    if "user" not in st.session_state or not st.session_state.get("strava_connected"):
        st.subheader("Connect Strava")
        st.info("Connect your Strava account to sync training data.")
        auth_url = auth.get_authorization_url()
        st.markdown(
            f'<div style="text-align:center;padding:20px">'
            f'<a href="{auth_url}" target="_blank">'
            f'<button style="background:#FC4C02;color:white;padding:12px 36px;font-size:16px;'
            f'font-weight:bold;border:none;border-radius:5px;cursor:pointer">🔗 Connect with Strava</button>'
            f'</a></div>',
            unsafe_allow_html=True,
        )
        # Manual fallback
        manual_url = st.text_input(
            "Or paste the redirect URL here:",
            placeholder="http://localhost:8501/Dashboard?code=XXXXX&scope=...",
        )
        if manual_url and "code=" in manual_url:
            m = re.search(r"code=([^&]+)", manual_url)
            if m:
                with st.spinner("Connecting..."):
                    try:
                        tokens = auth.exchange_code_for_token(m.group(1))
                        with get_db() as db:
                            user = _get_or_create_user(tokens, db)
                            st.session_state.user = {"id": user.id, "name": user.name}
                            st.session_state.strava_connected = True
                        st.success("Connected!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
    else:
        c1, c2 = st.columns([3, 1])
        with c1:
            st.success(f"✅ Strava connected — {st.session_state.user.get('name', '')}")
        with c2:
            if st.button("Disconnect", use_container_width=True):
                st.session_state.pop("user", None)
                st.session_state.pop("strava_connected", None)
                st.rerun()

        st.subheader("Sync Training Data")
        c1, c2 = st.columns(2)
        with c1:
            quick_sync = st.button("🔄 Quick Sync (7 days)", type="primary", use_container_width=True)
        with c2:
            full_sync = st.button("📥 Full Sync (3 months)", use_container_width=True)

        if quick_sync or full_sync:
            days = 7 if quick_sync else 90
            with st.spinner(f"Fetching Strava activities ({days} days)..."):
                try:
                    with get_db() as db:
                        user = db.query(User).filter(User.id == st.session_state.user["id"]).first()
                        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
                        if not profile:
                            # Create a default profile so sync can proceed
                            profile = UserProfile(user_id=user.id, ftp=200.0)
                            db.add(profile)
                            db.commit()
                            st.info("No FTP set — using 200W as default. Update it in Settings for accurate zones.")
                        token = _ensure_valid_token(user, db)
                        client = StravaDataClient(token)
                        after_date = datetime.now() - timedelta(days=days)
                        activities = client.get_activities(after=after_date, limit=200 if days == 90 else 50)

                    if not activities:
                        st.warning("No activities found.")
                        st.stop()

                    st.info(f"Found {len(activities)} activities — processing zones...")
                    progress_bar = st.progress(0)

                    with get_db() as db:
                        user = db.query(User).filter(User.id == st.session_state.user["id"]).first()
                        profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
                        processor = StravaDataProcessor(ftp=profile.ftp)
                        processed = processor.process_activities_batch(activities, fetch_streams=True, client=client)

                        new_count = updated_count = 0
                        for idx, act in enumerate(processed):
                            progress_bar.progress((idx + 1) / len(processed))
                            existing = db.query(Activity).filter(
                                Activity.strava_activity_id == act["id"]
                            ).first()
                            fields = dict(
                                name=act["name"], activity_type=act["type"],
                                start_date=act["start_date"], duration=act["moving_time"],
                                distance=act["distance"], average_watts=act.get("average_watts"),
                                normalized_power=act.get("normalized_power"),
                                tss=act.get("tss"), intensity_factor=act.get("intensity_factor"),
                                time_zone1=act.get("time_zone1", 0), time_zone2=act.get("time_zone2", 0),
                                time_zone3=act.get("time_zone3", 0), time_zone4=act.get("time_zone4", 0),
                                time_zone5=act.get("time_zone5", 0), time_zone6=act.get("time_zone6", 0),
                                time_zone7=act.get("time_zone7", 0),
                            )
                            if existing:
                                for k, v in fields.items():
                                    setattr(existing, k, v)
                                updated_count += 1
                            else:
                                db.add(Activity(user_id=user.id, strava_activity_id=act["id"], **fields))
                                new_count += 1

                        db.commit()
                        progress_bar.empty()

                        # Recalc CTL/ATL/TSB
                        all_acts = db.query(Activity).filter(Activity.user_id == user.id).all()
                        metrics = TrainingMetrics.calculate_ctl_atl_tsb(
                            [{"start_date": a.start_date, "tss": a.tss} for a in all_acts]
                        )
                        profile.ctl = metrics["ctl"]
                        profile.atl = metrics["atl"]
                        profile.tsb = metrics["tsb"]

                        # Power curve
                        three_months_ago = datetime.now() - timedelta(days=90)
                        recent_acts_data = [
                            {"max_watts": a.max_watts, "average_watts": a.average_watts,
                             "duration": a.duration, "start_date": a.start_date}
                            for a in all_acts
                            if a.start_date >= three_months_ago and a.max_watts and a.max_watts > 0
                        ]
                        if recent_acts_data:
                            best_efforts = calculate_best_efforts_from_activities(recent_acts_data)
                            for attr, key in [("best_5s","5s"),("best_15s","15s"),("best_30s","30s"),
                                              ("best_1min","1min"),("best_5min","5min"),
                                              ("best_20min","20min"),("best_60min","60min")]:
                                setattr(profile, attr, best_efforts.get(key))
                            all_time = {k: getattr(profile, f"pr_{k.replace('s','s').replace('min','min')}", 0) or 0
                                       for k in ["5s","15s","30s","1min","5min","20min","60min"]}
                            updated_pr = update_power_curve_with_pr_tracking(best_efforts, all_time)
                            for attr, key in [("pr_5s","5s"),("pr_15s","15s"),("pr_30s","30s"),
                                              ("pr_1min","1min"),("pr_5min","5min"),
                                              ("pr_20min","20min"),("pr_60min","60min")]:
                                setattr(profile, attr, updated_pr.get(key))
                            analyzer = PowerProfileAnalyzer(ftp=profile.ftp, weight=profile.weight or 75.0)
                            analysis = analyzer.analyze_from_best_efforts(best_efforts)
                            profile.rider_type = analysis["rider_type"]
                            profile.power_profile_json = json.dumps(analysis)

                        db.commit()

                        st.session_state.profile = {
                            "ftp": profile.ftp, "weight": profile.weight,
                            "ctl": profile.ctl, "atl": profile.atl, "tsb": profile.tsb,
                            "typical_workout_duration": 90,
                        }

                    st.success(f"Synced — {new_count} new, {updated_count} updated.")
                    c1, c2, c3 = st.columns(3)
                    c1.metric("CTL", f"{metrics['ctl']:.0f}")
                    c2.metric("ATL", f"{metrics['atl']:.0f}")
                    c3.metric("TSB", f"{metrics['tsb']:.1f}")
                    st.rerun()

                except Exception as e:
                    import traceback
                    st.error(f"Sync error: {e}")
                    st.code(traceback.format_exc())

        # Recent activities table
        if "user" in st.session_state:
            st.markdown("---")
            st.subheader("Recent Activities")
            with get_db() as db:
                acts = (
                    db.query(Activity)
                    .filter(Activity.user_id == st.session_state.user["id"])
                    .order_by(Activity.start_date.desc())
                    .limit(20)
                    .all()
                )
                # Extract into plain dicts INSIDE the session to avoid DetachedInstanceError
                rows = [
                    {"Date": a.start_date.strftime("%Y-%m-%d"), "Name": a.name,
                     "Type": a.activity_type, "Duration": f"{(a.duration or 0)//60}min",
                     "TSS": round(a.tss, 1) if a.tss else "N/A",
                     "NP": round(a.normalized_power, 0) if a.normalized_power else "N/A"}
                    for a in acts
                ]
            if rows:
                st.dataframe(rows, use_container_width=True)
            else:
                st.info("No activities synced yet.")
