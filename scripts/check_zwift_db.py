"""
Check Zwift workouts database statistics
"""
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.database import get_db
from src.database.models import ZwiftWorkout


def main():
    with get_db() as db:
        workouts = db.query(ZwiftWorkout).all()

        print("=" * 60)
        print("ZWIFT WORKOUTS DATABASE STATS")
        print("=" * 60)
        print(f"\nTotal workouts: {len(workouts)}")

        # Group by category
        categories = Counter(w.category for w in workouts if w.category)
        print(f"\nWorkouts by category ({len(categories)} categories):")
        for cat, count in categories.most_common(15):
            print(f"  {cat}: {count}")

        # Group by workout type
        types = Counter(w.workout_type for w in workouts if w.workout_type)
        print(f"\nWorkouts by type:")
        for wtype, count in types.most_common():
            print(f"  {wtype}: {count}")

        # Duration distribution
        print(f"\nDuration distribution:")
        short = len([w for w in workouts if w.duration_minutes and w.duration_minutes < 30])
        medium = len([w for w in workouts if w.duration_minutes and 30 <= w.duration_minutes < 60])
        long = len([w for w in workouts if w.duration_minutes and 60 <= w.duration_minutes < 90])
        very_long = len([w for w in workouts if w.duration_minutes and w.duration_minutes >= 90])
        print(f"  < 30min: {short}")
        print(f"  30-60min: {medium}")
        print(f"  60-90min: {long}")
        print(f"  >= 90min: {very_long}")

        # TSS distribution
        print(f"\nTSS distribution:")
        easy = len([w for w in workouts if w.tss and w.tss < 40])
        moderate = len([w for w in workouts if w.tss and 40 <= w.tss < 70])
        hard = len([w for w in workouts if w.tss and 70 <= w.tss < 100])
        very_hard = len([w for w in workouts if w.tss and w.tss >= 100])
        print(f"  < 40 TSS (Easy): {easy}")
        print(f"  40-70 TSS (Moderate): {moderate}")
        print(f"  70-100 TSS (Hard): {hard}")
        print(f"  >= 100 TSS (Very Hard): {very_hard}")

        # Sample workouts from each type
        print(f"\nSample workouts:")
        for wtype in ["Recovery", "Endurance", "Sweet Spot", "Threshold", "VO2max", "Anaerobic"]:
            sample = db.query(ZwiftWorkout).filter(ZwiftWorkout.workout_type == wtype).first()
            if sample:
                print(f"  {wtype}: {sample.name} ({sample.duration_minutes}min, TSS {sample.tss})")


if __name__ == "__main__":
    main()
