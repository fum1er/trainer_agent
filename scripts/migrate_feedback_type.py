"""
One-time migration: backfill workout_type on existing WorkoutFeedback rows
by copying from the associated WorkoutPlan.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.database import get_db, engine
from src.database.models import WorkoutFeedback, WorkoutPlan
from sqlalchemy import text

# Add column if it doesn't exist (SQLite doesn't support IF NOT EXISTS for columns)
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE workout_feedback ADD COLUMN workout_type VARCHAR"))
        conn.commit()
    print("Added workout_type column to workout_feedback table")
except Exception as e:
    if "duplicate column" in str(e).lower():
        print("Column workout_type already exists")
    else:
        print(f"Column may already exist: {e}")

# Backfill existing rows
with get_db() as db:
    feedbacks = db.query(WorkoutFeedback).filter(WorkoutFeedback.workout_type == None).all()
    updated = 0
    for fb in feedbacks:
        workout = db.query(WorkoutPlan).filter(WorkoutPlan.id == fb.workout_id).first()
        if workout and workout.workout_type:
            fb.workout_type = workout.workout_type
            updated += 1
    db.commit()
    print(f"Backfilled {updated}/{len(feedbacks)} feedback rows with workout_type")
