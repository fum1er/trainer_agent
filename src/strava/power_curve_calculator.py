"""
Calculate best power efforts from activities
"""
from typing import List, Dict
import numpy as np


def calculate_best_efforts_from_activities(activities: List[Dict]) -> Dict[str, float]:
    """
    Calculate best power efforts from activity data (simplified version)

    In a full implementation, this would analyze power streams.
    For now, uses heuristics based on max_watts and activity characteristics.

    Args:
        activities: List of activity dicts with average_watts, max_watts, duration

    Returns:
        Dict of duration -> best_watts
    """
    if not activities:
        return {}

    # Get max power from all activities
    max_power = max((act.get("max_watts", 0) for act in activities), default=0)

    if max_power == 0:
        return {}

    # Get best sustained powers from longer activities
    long_activities = [act for act in activities if act.get("duration", 0) > 1200]  # > 20 min

    if long_activities:
        # 20min power: highest average from 20+ min activities
        best_20min = max((act.get("average_watts", 0) for act in long_activities), default=0)

        # 60min power: highest average from 60+ min activities
        very_long = [act for act in activities if act.get("duration", 0) > 3600]
        best_60min = max((act.get("average_watts", 0) for act in very_long), default=best_20min * 0.95)
    else:
        best_20min = 0
        best_60min = 0

    # Estimate short efforts from max power
    # These are conservative estimates - real implementation would analyze streams
    best_efforts = {
        "5s": max_power * 0.95,      # 5% below absolute max
        "15s": max_power * 0.85,     # Sprint decay
        "30s": max_power * 0.75,     # Anaerobic capacity
        "1min": max_power * 0.60,    # VO2/Anaerobic
        "5min": best_20min * 1.10 if best_20min > 0 else max_power * 0.45,  # VO2max
        "20min": best_20min if best_20min > 0 else max_power * 0.35,  # FTP proxy
        "60min": best_60min if best_60min > 0 else best_20min * 0.95 if best_20min > 0 else max_power * 0.32,
    }

    # Filter out zeros
    return {k: v for k, v in best_efforts.items() if v > 0}


def update_power_curve_with_pr_tracking(
    current_best: Dict[str, float],
    all_time_pr: Dict[str, float]
) -> Dict[str, float]:
    """
    Update all-time PRs if current bests exceed them

    Args:
        current_best: Best efforts from last 3 months
        all_time_pr: All-time personal records

    Returns:
        Updated all-time PRs
    """
    updated_pr = all_time_pr.copy() if all_time_pr else {}

    for duration, watts in current_best.items():
        if watts > updated_pr.get(duration, 0):
            updated_pr[duration] = watts

    return updated_pr
