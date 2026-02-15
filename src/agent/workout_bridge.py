"""
Bridge between PlanAgent and WorkoutAgent for generating planned workouts
"""
from src.agent.workout_agent import WorkoutAgent
from src.database.models import PlannedWorkout, WorkoutPlan
from typing import Dict, List


def generate_planned_workout(
    planned_workout: PlannedWorkout,
    user_profile: Dict,
    training_history: List,
    feedback_history: List,
) -> Dict:
    """
    Generate a workout from a PlannedWorkout slot using WorkoutAgent.

    This is the bridge function that translates PlanAgent constraints
    into a format WorkoutAgent can understand.

    Args:
        planned_workout: PlannedWorkout model instance with constraints
        user_profile: Dict with FTP, CTL, ATL, TSB
        training_history: List of recent Activity dicts
        feedback_history: List of WorkoutFeedback dicts (type-aware)

    Returns:
        Dict with workout_xml, reasoning, structure (from WorkoutAgent)
    """
    # Build constrained request for WorkoutAgent
    user_input = f"""{planned_workout.instructions}

CONSTRAINTS FROM TRAINING PROGRAM:
- Workout Type: {planned_workout.workout_type}
- Target Duration: {planned_workout.target_duration} minutes
- Target TSS: {planned_workout.target_tss:.0f}

Please design a workout that matches these constraints as closely as possible.
"""

    # Add program context to profile
    profile_with_context = {
        **user_profile,
        "target_workout_type": planned_workout.workout_type,
    }

    # Initialize WorkoutAgent and generate
    agent = WorkoutAgent()
    result = agent.generate_workout(
        user_input=user_input,
        user_profile=profile_with_context,
        training_history=training_history,
        feedback_history=feedback_history,
    )

    return result


def validate_workout_constraints(
    generated_workout: Dict, planned_workout: PlannedWorkout, tolerance: float = 0.15
) -> Dict:
    """
    Validate that the generated workout matches the planned constraints.

    Args:
        generated_workout: Result from WorkoutAgent (structure dict)
        planned_workout: PlannedWorkout model instance
        tolerance: Allowed deviation (e.g., 0.15 = ±15%)

    Returns:
        Dict with is_valid, warnings, actual_vs_target
    """
    structure = generated_workout.get("workout_structure", {})
    actual_tss = structure.get("target_tss", 0)
    actual_duration = structure.get("target_duration", 0)
    actual_type = structure.get("workout_type", "")

    target_tss = planned_workout.target_tss
    target_duration = planned_workout.target_duration
    target_type = planned_workout.workout_type

    warnings = []
    is_valid = True

    # Check TSS
    tss_diff = abs(actual_tss - target_tss) / target_tss if target_tss > 0 else 0
    if tss_diff > tolerance:
        is_valid = False
        warnings.append(
            f"TSS mismatch: generated {actual_tss:.0f}, target {target_tss:.0f} ({tss_diff:.0%} deviation)"
        )

    # Check duration
    duration_diff = (
        abs(actual_duration - target_duration) / target_duration if target_duration > 0 else 0
    )
    if duration_diff > tolerance:
        is_valid = False
        warnings.append(
            f"Duration mismatch: generated {actual_duration}min, target {target_duration}min ({duration_diff:.0%} deviation)"
        )

    # Check type
    if actual_type.lower() != target_type.lower():
        warnings.append(f"Type mismatch: generated '{actual_type}', target '{target_type}'")
        # Type mismatch is a soft warning, not a hard failure

    return {
        "is_valid": is_valid,
        "warnings": warnings,
        "actual_vs_target": {
            "tss": {"actual": actual_tss, "target": target_tss, "diff_pct": tss_diff},
            "duration": {"actual": actual_duration, "target": target_duration, "diff_pct": duration_diff},
            "type": {"actual": actual_type, "target": target_type, "match": actual_type.lower() == target_type.lower()},
        },
    }


def batch_generate_week_workouts(
    planned_workouts: List[PlannedWorkout],
    user_profile: Dict,
    training_history: List,
    feedback_history: List,
    fail_on_validation: bool = False,
) -> List[Dict]:
    """
    Generate all workouts for a week in batch.

    Args:
        planned_workouts: List of PlannedWorkout instances for the week
        user_profile: Dict with FTP, CTL, ATL, TSB
        training_history: List of recent Activity dicts
        feedback_history: List of WorkoutFeedback dicts
        fail_on_validation: If True, raise exception on validation failure

    Returns:
        List of dicts with workout_xml, reasoning, structure, validation
    """
    results = []

    for planned_workout in planned_workouts:
        try:
            # Generate workout
            result = generate_planned_workout(
                planned_workout=planned_workout,
                user_profile=user_profile,
                training_history=training_history,
                feedback_history=feedback_history,
            )

            # Validate constraints
            validation = validate_workout_constraints(result, planned_workout)

            if fail_on_validation and not validation["is_valid"]:
                raise ValueError(f"Workout validation failed: {validation['warnings']}")

            result["validation"] = validation
            results.append(result)

        except Exception as e:
            print(f"Failed to generate workout {planned_workout.id}: {e}")
            results.append({
                "error": str(e),
                "planned_workout_id": planned_workout.id,
                "workout_xml": None,
            })

    return results
