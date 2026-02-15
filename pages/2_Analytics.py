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
from src.visualization.charts import create_pmc_chart, create_weekly_tss_chart, create_zone_distribution_chart, create_power_curve_spider_chart
from src.strava.power_profile import PowerProfileAnalyzer
from src.strava.power_curve_calculator import calculate_best_efforts_from_activities, update_power_curve_with_pr_tracking
from datetime import datetime, timedelta


def ensure_valid_token(user, db):
    """
    Check if access token is expired and refresh if needed

    Args:
        user: User object from database
        db: Database session

    Returns:
        Valid access token
    """
    # Check if token is expired or about to expire (within 5 minutes)
    if user.strava_token_expires_at and user.strava_token_expires_at < datetime.utcnow() + timedelta(minutes=5):
        st.info("🔄 Refreshing Strava token...")

        # Refresh the token
        auth = StravaAuth()
        try:
            new_tokens = auth.refresh_access_token(user.strava_refresh_token)

            # Update user in database
            user.strava_access_token = new_tokens["access_token"]
            user.strava_refresh_token = new_tokens["refresh_token"]
            user.strava_token_expires_at = new_tokens["expires_at"]
            db.commit()

            st.success("✅ Token refreshed!")
            return new_tokens["access_token"]
        except Exception as e:
            st.error(f"❌ Failed to refresh token: {e}")
            st.warning("Please reconnect your Strava account")
            raise

    return user.strava_access_token


st.title("📊 Analytics & Strava Sync")

# Strava OAuth section
st.subheader("Strava Connection")


def _get_or_create_user(tokens, db):
    """Find existing user or create one. Never create duplicates."""
    # Look for existing user first
    user = db.query(User).first()
    if user:
        # Update tokens on existing user
        user.strava_access_token = tokens["access_token"]
        user.strava_refresh_token = tokens["refresh_token"]
        user.strava_token_expires_at = tokens["expires_at"]
        db.commit()
        return user
    else:
        # First time: create user
        user = User(
            name="Strava User",
            strava_access_token=tokens["access_token"],
            strava_refresh_token=tokens["refresh_token"],
            strava_token_expires_at=tokens["expires_at"],
        )
        db.add(user)
        db.commit()
        return user


# Auto-load existing user from DB on page load
if "user" not in st.session_state or not st.session_state.get("strava_connected"):
    with get_db() as db:
        existing_user = db.query(User).filter(User.strava_access_token.isnot(None)).first()
        if existing_user:
            st.session_state.user = {"id": existing_user.id, "name": existing_user.name}
            st.session_state.strava_connected = True

if "user" not in st.session_state or not st.session_state.get("strava_connected"):
    auth = StravaAuth()

    # Check if we just got back from Strava OAuth (code in URL)
    query_params = st.query_params
    auth_code = query_params.get("code", None)

    if auth_code and not st.session_state.get("processing_auth"):
        st.session_state.processing_auth = True
        st.info("🔄 Completing Strava connection...")

        try:
            tokens = auth.exchange_code_for_token(auth_code)

            with get_db() as db:
                user = _get_or_create_user(tokens, db)
                st.session_state.user = {"id": user.id, "name": user.name}
                st.session_state.strava_connected = True

            # Clear query params and rerun
            st.query_params.clear()
            st.session_state.pop("processing_auth", None)
            st.success("✅ Strava connected successfully!")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Error connecting to Strava: {e}")
            st.session_state.pop("processing_auth", None)
            st.query_params.clear()
    else:
        # Show connect button
        st.info("🚴 Connect your Strava account to sync your training data")

        auth_url = auth.get_authorization_url()

        st.markdown(
            f"""
            <div style="text-align: center; padding: 20px;">
                <a href="{auth_url}" target="_blank">
                    <button style="
                        background-color: #FC4C02;
                        color: white;
                        padding: 15px 40px;
                        font-size: 18px;
                        font-weight: bold;
                        border: none;
                        border-radius: 5px;
                        cursor: pointer;
                    ">
                        🔗 Connect with Strava
                    </button>
                </a>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.info(
            "💡 **How it works:**\n"
            "1. Click the button above\n"
            "2. Authorize the app on Strava\n"
            "3. You'll be redirected back automatically\n\n"
            "⚠️ If the redirect doesn't work, copy the full URL after authorization and paste it here:"
        )

        # Fallback: manual code input
        manual_url = st.text_input(
            "Or paste the redirect URL here:",
            placeholder="http://localhost:8501/Analytics?code=XXXXX&scope=...",
            key="manual_url_input"
        )

        if manual_url and "code=" in manual_url:
            import re
            code_match = re.search(r'code=([^&]+)', manual_url)
            if code_match:
                code = code_match.group(1)
                with st.spinner("Connecting to Strava..."):
                    try:
                        tokens = auth.exchange_code_for_token(code)

                        with get_db() as db:
                            user = _get_or_create_user(tokens, db)
                            st.session_state.user = {"id": user.id, "name": user.name}
                            st.session_state.strava_connected = True
                            st.success("✅ Strava connected successfully!")
                            st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error connecting to Strava: {e}")
else:
    col1, col2 = st.columns([3, 1])
    with col1:
        st.success("✅ Strava connected!")
    with col2:
        if st.button("🔄 Reconnect", use_container_width=True):
            # Clear session and force re-auth
            del st.session_state.user
            del st.session_state.strava_connected
            st.rerun()

    # Sync section
    st.subheader("Sync Training Data")

    col1, col2 = st.columns(2)

    with col1:
        quick_sync = st.button("🔄 Quick Sync (Last 7 Days)", type="primary", use_container_width=True)

    with col2:
        full_sync = st.button("📥 Full Sync (Last 3 Months)", use_container_width=True)

    if quick_sync or full_sync:
        sync_type = "Quick sync (last 7 days)" if quick_sync else "Full sync (last 3 months)"
        with st.spinner(f"Fetching activities from Strava ({sync_type})..."):
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

                    # Ensure token is valid (refresh if expired)
                    valid_token = ensure_valid_token(user, db)

                    # Fetch activities
                    client = StravaDataClient(valid_token)

                    # Quick sync: only last 7 days
                    if quick_sync:
                        after_date = datetime.now() - timedelta(days=7)
                        activities = client.get_activities(after=after_date, limit=50)
                    else:
                        # Full sync: last 3 months
                        after_date = datetime.now() - timedelta(days=90)
                        activities = client.get_activities(after=after_date, limit=100)

                    if not activities:
                        st.warning("No activities found in the selected time period.")
                        st.stop()

                    st.info(f"Found {len(activities)} activities. Processing with power zones...")

                    # Process activities with streams for zone distribution
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    processor = StravaDataProcessor(ftp=profile.ftp)
                    processed = processor.process_activities_batch(
                        activities,
                        fetch_streams=True,  # Enable zone calculation
                        client=client
                    )

                    # Store in database (upsert to avoid duplicates)
                    new_count = 0
                    updated_count = 0

                    for idx, activity_data in enumerate(processed):
                        progress = (idx + 1) / len(processed)
                        progress_bar.progress(progress)
                        status_text.text(f"Saving activity {idx + 1}/{len(processed)}: {activity_data.get('name', 'Unknown')}")
                        # Check if activity already exists
                        existing = db.query(Activity).filter(
                            Activity.strava_activity_id == activity_data["id"]
                        ).first()

                        if existing:
                            # Update existing activity
                            existing.name = activity_data["name"]
                            existing.activity_type = activity_data["type"]
                            existing.start_date = activity_data["start_date"]
                            existing.duration = activity_data["moving_time"]
                            existing.distance = activity_data["distance"]
                            existing.average_watts = activity_data.get("average_watts")
                            existing.normalized_power = activity_data.get("normalized_power")
                            existing.tss = activity_data.get("tss")
                            existing.intensity_factor = activity_data.get("intensity_factor")
                            existing.time_zone1 = activity_data.get("time_zone1", 0)
                            existing.time_zone2 = activity_data.get("time_zone2", 0)
                            existing.time_zone3 = activity_data.get("time_zone3", 0)
                            existing.time_zone4 = activity_data.get("time_zone4", 0)
                            existing.time_zone5 = activity_data.get("time_zone5", 0)
                            existing.time_zone6 = activity_data.get("time_zone6", 0)
                            existing.time_zone7 = activity_data.get("time_zone7", 0)
                            updated_count += 1
                        else:
                            # Create new activity
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
                                # Zone distribution (from streams)
                                time_zone1=activity_data.get("time_zone1", 0),
                                time_zone2=activity_data.get("time_zone2", 0),
                                time_zone3=activity_data.get("time_zone3", 0),
                                time_zone4=activity_data.get("time_zone4", 0),
                                time_zone5=activity_data.get("time_zone5", 0),
                                time_zone6=activity_data.get("time_zone6", 0),
                                time_zone7=activity_data.get("time_zone7", 0),
                            )
                            db.add(activity)
                            new_count += 1

                    db.commit()
                    progress_bar.empty()
                    status_text.empty()

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

                    # Calculate power curve from last 3 months
                    three_months_ago = datetime.now() - timedelta(days=90)
                    recent_activities_data = [
                        {
                            "max_watts": a.max_watts,
                            "average_watts": a.average_watts,
                            "duration": a.duration,
                            "start_date": a.start_date,
                        }
                        for a in db.query(Activity)
                        .filter(Activity.user_id == user.id, Activity.start_date >= three_months_ago)
                        .all()
                        if a.max_watts and a.max_watts > 0
                    ]

                    if recent_activities_data:
                        # Calculate best efforts
                        best_efforts = calculate_best_efforts_from_activities(recent_activities_data)

                        # Store in profile
                        profile.best_5s = best_efforts.get("5s")
                        profile.best_15s = best_efforts.get("15s")
                        profile.best_30s = best_efforts.get("30s")
                        profile.best_1min = best_efforts.get("1min")
                        profile.best_5min = best_efforts.get("5min")
                        profile.best_20min = best_efforts.get("20min")
                        profile.best_60min = best_efforts.get("60min")

                        # Update PRs if current bests exceed them
                        all_time_pr = {
                            "5s": profile.pr_5s or 0,
                            "15s": profile.pr_15s or 0,
                            "30s": profile.pr_30s or 0,
                            "1min": profile.pr_1min or 0,
                            "5min": profile.pr_5min or 0,
                            "20min": profile.pr_20min or 0,
                            "60min": profile.pr_60min or 0,
                        }
                        updated_pr = update_power_curve_with_pr_tracking(best_efforts, all_time_pr)

                        profile.pr_5s = updated_pr.get("5s")
                        profile.pr_15s = updated_pr.get("15s")
                        profile.pr_30s = updated_pr.get("30s")
                        profile.pr_1min = updated_pr.get("1min")
                        profile.pr_5min = updated_pr.get("5min")
                        profile.pr_20min = updated_pr.get("20min")
                        profile.pr_60min = updated_pr.get("60min")

                        # Analyze rider profile
                        analyzer = PowerProfileAnalyzer(ftp=profile.ftp, weight=profile.weight or 75.0)
                        analysis = analyzer.analyze_from_best_efforts(best_efforts)

                        profile.rider_type = analysis["rider_type"]
                        import json
                        profile.power_profile_json = json.dumps(analysis)

                    db.commit()

                    # Update session state with new metrics
                    st.session_state.profile = {
                        "ftp": profile.ftp,
                        "weight": profile.weight,
                        "ctl": profile.ctl,
                        "atl": profile.atl,
                        "tsb": profile.tsb,
                        "typical_workout_duration": 90,
                    }

                    st.success(f"✅ Synced {len(processed)} activities!")
                    col1, col2, col3 = st.columns(3)
                    col1.metric("CTL", f"{metrics['ctl']:.0f}")
                    col2.metric("ATL", f"{metrics['atl']:.0f}")
                    col3.metric("TSB", f"{metrics['tsb']:.1f}")
                    if profile.rider_type:
                        st.info(f"🚴 Rider Profile: {profile.rider_type.replace('_', ' ').title()}")

                    # Auto-refresh page to show new data
                    st.rerun()

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

            # Add charts if we have enough data
            st.markdown("---")
            st.subheader("Training Analytics")

            # Get last 90 days for PMC
            recent_activities = db.query(Activity).filter(
                Activity.user_id == st.session_state.user["id"],
                Activity.start_date >= datetime.now() - timedelta(days=90)
            ).order_by(Activity.start_date).all()

            if len(recent_activities) > 5:
                activity_data = [
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
                    for a in recent_activities
                ]

                # PMC Chart
                st.plotly_chart(create_pmc_chart(activity_data), use_container_width=True)

                # Power Profile Spider Chart
                profile = db.query(UserProfile).filter(UserProfile.user_id == st.session_state.user["id"]).first()
                if profile and profile.best_5s:
                    st.markdown("---")
                    st.subheader("Power Profile Analysis")

                    # Build power curve dict
                    power_curve = {
                        "5s": profile.best_5s,
                        "15s": profile.best_15s,
                        "30s": profile.best_30s,
                        "1min": profile.best_1min,
                        "5min": profile.best_5min,
                        "20min": profile.best_20min,
                        "60min": profile.best_60min,
                    }
                    # Remove None values
                    power_curve = {k: v for k, v in power_curve.items() if v is not None}

                    # Recalculate percentiles
                    analyzer = PowerProfileAnalyzer(ftp=profile.ftp, weight=profile.weight or 75.0)
                    analysis = analyzer.analyze_from_best_efforts(power_curve)

                    # Show spider chart
                    spider_fig = create_power_curve_spider_chart(
                        power_curve=power_curve,
                        percentiles=analysis["percentiles"],
                        rider_type=analysis["rider_type"]
                    )
                    st.plotly_chart(spider_fig, use_container_width=True)

                    # Show recommendations
                    st.info(f"**Recommendations:** {analysis['recommendations']}")

                    # Show strengths/weaknesses
                    col1, col2 = st.columns(2)
                    with col1:
                        if analysis["strengths"]:
                            st.success(f"**Strengths:** {', '.join(analysis['strengths'])}")
                        else:
                            st.caption("No dominant strengths identified")
                    with col2:
                        if analysis["weaknesses"]:
                            st.warning(f"**Weaknesses:** {', '.join(analysis['weaknesses'])}")
                        else:
                            st.caption("No major weaknesses identified")

                st.markdown("---")

                # Weekly TSS and Zone Distribution
                col1, col2 = st.columns(2)
                with col1:
                    st.plotly_chart(create_weekly_tss_chart(activity_data), use_container_width=True)
                with col2:
                    st.plotly_chart(create_zone_distribution_chart(activity_data), use_container_width=True)
            else:
                st.info("Sync more activities to see analytics charts (need at least 5 activities)")

        else:
            st.info("No activities synced yet. Click 'Sync Last 6 Months' above.")
