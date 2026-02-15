"""
Migration: Add power curve columns to UserProfile and clear old feedback
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.database import get_db, engine
from src.database.models import WorkoutFeedback
from sqlalchemy import text

print("=== Migration: Power Curve + Feedback Cleanup ===\n")

# Add power curve columns
power_curve_columns = [
    ("best_5s", "FLOAT"),
    ("best_15s", "FLOAT"),
    ("best_30s", "FLOAT"),
    ("best_1min", "FLOAT"),
    ("best_5min", "FLOAT"),
    ("best_20min", "FLOAT"),
    ("best_60min", "FLOAT"),
    ("pr_5s", "FLOAT"),
    ("pr_15s", "FLOAT"),
    ("pr_30s", "FLOAT"),
    ("pr_1min", "FLOAT"),
    ("pr_5min", "FLOAT"),
    ("pr_20min", "FLOAT"),
    ("pr_60min", "FLOAT"),
    ("rider_type", "VARCHAR"),
    ("power_profile_json", "TEXT"),
]

print("1. Adding power curve columns to user_profiles...")
with engine.connect() as conn:
    for col_name, col_type in power_curve_columns:
        try:
            conn.execute(text(f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_type}"))
            conn.commit()
            print(f"   ✓ Added {col_name}")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print(f"   - {col_name} already exists")
            else:
                print(f"   ✗ Error adding {col_name}: {e}")

# Clear old feedback
print("\n2. Clearing old workout feedback...")
with get_db() as db:
    count = db.query(WorkoutFeedback).count()
    if count > 0:
        db.query(WorkoutFeedback).delete()
        db.commit()
        print(f"   ✓ Deleted {count} old feedback records")
    else:
        print("   - No feedback to delete")

print("\n✅ Migration complete!")
print("\nNext steps:")
print("  - Sync Strava activities in Analytics page")
print("  - Power curve will be calculated from last 3 months")
print("  - Spider chart will show your rider profile")
