"""
Power profile analysis - determine rider strengths/weaknesses
"""
from typing import Dict, List
import numpy as np


class PowerProfileAnalyzer:
    """Analyze rider's power curve to determine strengths/weaknesses"""

    # Standard durations for power curve (seconds)
    DURATIONS = {
        "5s": 5,
        "15s": 15,
        "30s": 30,
        "1min": 60,
        "5min": 300,
        "20min": 1200,
        "60min": 3600,
    }

    # Reference power curve for cat 1/2 cyclist (W/kg) - from Coggan/Allen
    REFERENCE_CURVE = {
        "5s": 24.0,      # Neuromuscular
        "15s": 18.5,     # Anaerobic
        "30s": 15.0,     # Anaerobic
        "1min": 12.0,    # Anaerobic/VO2
        "5min": 6.5,     # VO2max
        "20min": 5.0,    # FTP/Threshold
        "60min": 4.5,    # Endurance
    }

    def __init__(self, ftp: float, weight: float = 75.0):
        """
        Initialize analyzer

        Args:
            ftp: Functional Threshold Power (watts)
            weight: Rider weight (kg)
        """
        self.ftp = ftp
        self.weight = weight

    def analyze_from_best_efforts(self, best_efforts: Dict[str, float]) -> Dict:
        """
        Analyze rider profile from best power efforts

        Args:
            best_efforts: Dict of duration -> watts (e.g. {"5s": 1200, "1min": 400})

        Returns:
            Dict with profile analysis
        """
        # Convert to W/kg
        power_curve_wkg = {
            duration: watts / self.weight
            for duration, watts in best_efforts.items()
            if watts > 0
        }

        # Calculate percentiles vs reference
        percentiles = {}
        for duration, wkg in power_curve_wkg.items():
            ref = self.REFERENCE_CURVE.get(duration)
            if ref:
                percentiles[duration] = (wkg / ref) * 100

        # Identify strengths and weaknesses
        strengths = []
        weaknesses = []

        for duration, pct in sorted(percentiles.items(), key=lambda x: x[1], reverse=True):
            if pct >= 90:
                strengths.append(duration)
            elif pct < 70:
                weaknesses.append(duration)

        # Determine rider type
        rider_type = self._classify_rider_type(percentiles)

        return {
            "power_curve_watts": best_efforts,
            "power_curve_wkg": power_curve_wkg,
            "percentiles": percentiles,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "rider_type": rider_type,
            "recommendations": self._generate_recommendations(rider_type, weaknesses),
        }

    def _classify_rider_type(self, percentiles: Dict[str, float]) -> str:
        """Classify rider as sprinter, puncheur, rouleur, climber, etc."""
        if not percentiles:
            return "balanced"

        # Calculate scores for different durations
        sprint_score = np.mean([percentiles.get("5s", 0), percentiles.get("15s", 0), percentiles.get("30s", 0)])
        vo2_score = np.mean([percentiles.get("1min", 0), percentiles.get("5min", 0)])
        threshold_score = percentiles.get("20min", 0)
        endurance_score = percentiles.get("60min", 0)

        scores = {
            "sprinter": sprint_score,
            "puncheur": (sprint_score * 0.4 + vo2_score * 0.6),
            "pursuiter": (vo2_score * 0.5 + threshold_score * 0.5),
            "time_trialist": (threshold_score * 0.6 + endurance_score * 0.4),
            "climber": (vo2_score * 0.3 + threshold_score * 0.5 + endurance_score * 0.2),
        }

        # Return highest score
        rider_type = max(scores.items(), key=lambda x: x[1])[0]

        # If scores are close, return "all-rounder"
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) >= 2 and sorted_scores[0] - sorted_scores[1] < 10:
            return "all_rounder"

        return rider_type

    def _generate_recommendations(self, rider_type: str, weaknesses: List[str]) -> str:
        """Generate training recommendations based on profile"""
        recommendations = []

        # Rider type specific
        type_recs = {
            "sprinter": "Focus on maximal power and neuromuscular development. Don't neglect threshold work for race-long endurance.",
            "puncheur": "Maintain your explosive power while building threshold and VO2max for longer climbs.",
            "pursuiter": "Strong VO2max and threshold - work on sustaining high power for longer efforts.",
            "time_trialist": "Excellent sustained power. Add some VO2max and sprint work for race dynamics.",
            "climber": "Good sustained power. Add force and sprint work for attacks and accelerations.",
            "all_rounder": "Well-balanced profile. Focus on race-specific demands.",
        }

        recommendations.append(type_recs.get(rider_type, "Balanced training approach recommended."))

        # Weakness-specific
        if weaknesses:
            weak_zones = []
            for w in weaknesses:
                if w in ["5s", "15s", "30s"]:
                    weak_zones.append("Sprint/Neuromuscular")
                elif w in ["1min", "5min"]:
                    weak_zones.append("VO2max/Anaerobic")
                elif w == "20min":
                    weak_zones.append("Threshold/FTP")
                elif w == "60min":
                    weak_zones.append("Endurance")

            unique_zones = list(set(weak_zones))
            if unique_zones:
                recommendations.append(f"Address weaknesses in: {', '.join(unique_zones)}")

        return " ".join(recommendations)

    def estimate_best_efforts_from_activities(self, activities: List[Dict]) -> Dict[str, float]:
        """
        Estimate best power efforts from activity data (fallback when no power curve data)

        Args:
            activities: List of activity dicts with average_watts, duration, max_watts

        Returns:
            Dict of duration -> estimated_watts
        """
        # Simplified estimation based on max watts and FTP
        # In real implementation, would analyze power streams
        best_efforts = {}

        max_power = max((act.get("max_watts", 0) for act in activities), default=0)
        avg_threshold = np.mean([
            act.get("average_watts", 0)
            for act in activities
            if act.get("duration", 0) > 1200  # Activities > 20min
        ]) if activities else self.ftp

        # Rough estimates based on typical power duration curve
        if max_power > 0:
            best_efforts["5s"] = max_power * 0.95  # 95% of max
            best_efforts["15s"] = max_power * 0.85
            best_efforts["30s"] = max_power * 0.75
            best_efforts["1min"] = self.ftp * 1.20
            best_efforts["5min"] = self.ftp * 1.10
            best_efforts["20min"] = self.ftp * 1.00
            best_efforts["60min"] = self.ftp * 0.95

        return best_efforts
