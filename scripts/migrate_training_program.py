"""
Migration script to add TrainingProgram, WeekPlan, and PlannedWorkout tables
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.database import get_db, init_db
from src.database.models import Base, TrainingProgram, WeekPlan, PlannedWorkout
from sqlalchemy import inspect


def main():
    print("Starting training program tables migration...")

    # Initialize database (creates tables if they don't exist)
    init_db()

    # Verify tables were created
    with get_db() as db:
        inspector = inspect(db.bind)
        tables = inspector.get_table_names()

        required_tables = ["training_programs", "week_plans", "planned_workouts"]

        for table in required_tables:
            if table in tables:
                print(f"✓ Table '{table}' exists")
            else:
                print(f"✗ Table '{table}' missing!")

        # Count existing records
        program_count = db.query(TrainingProgram).count()
        week_count = db.query(WeekPlan).count()
        workout_count = db.query(PlannedWorkout).count()

        print(f"\nCurrent record counts:")
        print(f"  - TrainingProgram: {program_count}")
        print(f"  - WeekPlan: {week_count}")
        print(f"  - PlannedWorkout: {workout_count}")

    print("\nMigration complete!")


if __name__ == "__main__":
    main()
