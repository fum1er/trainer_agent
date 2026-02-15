"""
Generate RAG documents from ZwiftWorkout database
Creates formatted text documents for embedding into vector DB
"""
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.database import get_db
from src.database.models import ZwiftWorkout


def format_workout_as_rag_doc(workout):
    """
    Format a ZwiftWorkout as a RAG document with all relevant info

    Returns:
        Dict with 'text' and 'metadata'
    """
    # Format intervals as human-readable text
    intervals_text = []
    if workout.structure_json and isinstance(workout.structure_json, dict):
        intervals = workout.structure_json.get('intervals', [])

        for i, interval in enumerate(intervals, 1):
            if interval.get('type') == 'SteadyState':
                duration_min = interval.get('duration', 0) // 60
                power_pct = int(interval.get('power', 0) * 100)
                cadence = interval.get('cadence')
                cadence_str = f" @ {cadence}rpm" if cadence else ""

                intervals_text.append(
                    f"  {i}. Steady: {duration_min}min at {power_pct}% FTP{cadence_str}"
                )

            elif interval.get('type') in ['Warmup', 'Cooldown']:
                duration_min = interval.get('duration', 0) // 60
                power_low = int(interval.get('power_low', 0) * 100)
                power_high = int(interval.get('power_high', 0) * 100)

                intervals_text.append(
                    f"  {i}. {interval['type']}: {duration_min}min from {power_low}% to {power_high}% FTP"
                )

    # Format zones
    zones_text = []
    if workout.structure_json and isinstance(workout.structure_json, dict):
        stats = workout.structure_json.get('stats', {})
        zone_dist = stats.get('zone_distribution', {})
        if zone_dist:
            for zone in ['Z1', 'Z2', 'Z3', 'Z4', 'Z5', 'Z6', 'Z7']:
                time = zone_dist.get(zone)
                if time and time != '-':
                    zones_text.append(f"{zone}: {time}")

    # Build the document
    doc_text = f"""# Zwift Workout: {workout.name}

**Category**: {workout.category or 'General'}
**Type**: {workout.workout_type}
**Duration**: {workout.duration_minutes} minutes
**TSS**: {workout.tss}
**Intensity Factor**: {workout.intensity_factor}
**Difficulty**: {workout.difficulty_level}/5

## Description
{workout.description or 'No description available.'}

## Training Focus
{workout.training_focus or f'{workout.workout_type} workout'}

## Workout Structure
{chr(10).join(intervals_text) if intervals_text else 'Interval structure not available.'}

## Zone Distribution
{', '.join(zones_text) if zones_text else 'Zone distribution not available.'}

## Use Cases
{workout.use_cases or 'General training'}

## Source
{workout.source_url}
"""

    # Metadata for filtering
    metadata = {
        'workout_id': workout.id,
        'name': workout.name,
        'category': workout.category or 'General',
        'workout_type': workout.workout_type,
        'duration_minutes': workout.duration_minutes,
        'tss': workout.tss,
        'difficulty_level': workout.difficulty_level,
        'source_url': workout.source_url,
    }

    return {
        'text': doc_text,
        'metadata': metadata
    }


def main():
    """Generate RAG documents from all Zwift workouts in DB"""
    print("=" * 60)
    print("GENERATE RAG DOCUMENTS FROM ZWIFT WORKOUTS")
    print("=" * 60)

    output_dir = Path("data/zwift_rag_docs")
    output_dir.mkdir(parents=True, exist_ok=True)

    with get_db() as db:
        workouts = db.query(ZwiftWorkout).all()

        print(f"\nFound {len(workouts)} workouts in database")
        print(f"Generating RAG documents...\n")

        generated = 0
        skipped = 0

        for workout in workouts:
            try:
                # Generate document
                doc = format_workout_as_rag_doc(workout)

                # Clean filename
                filename = f"{workout.id:05d}_{workout.name[:50]}.txt"
                filename = filename.replace('/', '_').replace('\\', '_').replace(':', '_')

                filepath = output_dir / filename

                # Write text file
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(doc['text'])

                generated += 1

                if generated % 100 == 0:
                    print(f"  Generated {generated}/{len(workouts)}...")

            except Exception as e:
                print(f"  Error generating doc for {workout.name}: {e}")
                skipped += 1
                continue

        # Save metadata index
        metadata_file = output_dir / "metadata_index.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump({
                'total_workouts': len(workouts),
                'generated_docs': generated,
                'skipped': skipped,
                'output_dir': str(output_dir),
            }, f, indent=2)

        print(f"\n{'='*60}")
        print(f"DONE!")
        print(f"{'='*60}")
        print(f"Generated: {generated} documents")
        print(f"Skipped: {skipped}")
        print(f"Output: {output_dir}")
        print(f"\nNext step: Process these documents with document_processor.py")


if __name__ == "__main__":
    main()
