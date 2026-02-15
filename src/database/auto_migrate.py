"""
Auto-migration system - runs on app startup
"""
from sqlalchemy import text, inspect
from .database import engine, get_db
from .models import WorkoutFeedback
import logging

logger = logging.getLogger(__name__)


def auto_migrate():
    """
    Auto-migrate database schema on startup.
    Safe to run multiple times - checks if columns exist before adding.
    """
    migrations = []

    # Power curve columns for UserProfile
    power_curve_columns = [
        ("user_profiles", "best_5s", "FLOAT"),
        ("user_profiles", "best_15s", "FLOAT"),
        ("user_profiles", "best_30s", "FLOAT"),
        ("user_profiles", "best_1min", "FLOAT"),
        ("user_profiles", "best_5min", "FLOAT"),
        ("user_profiles", "best_20min", "FLOAT"),
        ("user_profiles", "best_60min", "FLOAT"),
        ("user_profiles", "pr_5s", "FLOAT"),
        ("user_profiles", "pr_15s", "FLOAT"),
        ("user_profiles", "pr_30s", "FLOAT"),
        ("user_profiles", "pr_1min", "FLOAT"),
        ("user_profiles", "pr_5min", "FLOAT"),
        ("user_profiles", "pr_20min", "FLOAT"),
        ("user_profiles", "pr_60min", "FLOAT"),
        ("user_profiles", "rider_type", "VARCHAR"),
        ("user_profiles", "power_profile_json", "TEXT"),
    ]

    with engine.connect() as conn:
        inspector = inspect(engine)

        # Check and add missing columns
        for table_name, col_name, col_type in power_curve_columns:
            if table_name in inspector.get_table_names():
                existing_cols = [col["name"] for col in inspector.get_columns(table_name)]
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
                        migrations.append(f"Added {table_name}.{col_name}")
                        logger.info(f"Migration: Added {table_name}.{col_name}")
                    except Exception as e:
                        logger.error(f"Failed to add {table_name}.{col_name}: {e}")

    # One-time cleanup: clear old feedback (only if workout_type column exists but data is pre-refactor)
    try:
        with get_db() as db:
            # Check if there's old feedback without workout_type
            old_feedback_count = db.query(WorkoutFeedback).filter(
                WorkoutFeedback.workout_type == None
            ).count()

            if old_feedback_count > 10:  # Arbitrary threshold - if lots of old data
                logger.info(f"Cleaning {old_feedback_count} old feedback records (pre-refactor)")
                db.query(WorkoutFeedback).delete()
                db.commit()
                migrations.append(f"Cleaned {old_feedback_count} old feedback records")
    except Exception as e:
        logger.error(f"Failed to clean old feedback: {e}")

    return migrations


def get_migration_status():
    """Check which migrations are needed"""
    with engine.connect() as conn:
        inspector = inspect(engine)

        if "user_profiles" not in inspector.get_table_names():
            return {"status": "error", "message": "Database not initialized"}

        existing_cols = [col["name"] for col in inspector.get_columns("user_profiles")]

        power_curve_cols = ["best_5s", "best_15s", "best_30s", "best_1min", "best_5min",
                           "best_20min", "best_60min", "pr_5s", "rider_type", "power_profile_json"]

        missing = [col for col in power_curve_cols if col not in existing_cols]

        if missing:
            return {
                "status": "needs_migration",
                "missing_columns": missing,
                "message": f"Missing {len(missing)} power curve columns"
            }

        return {"status": "up_to_date", "message": "All migrations applied"}
