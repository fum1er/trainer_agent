"""
Adaptation Engine for training program adjustments based on actual performance
"""
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class AdaptationEngine:
    """
    Deterministic adaptation rules for training program re-planning.
    Analyzes compliance (planned vs actual) and rider fatigue to produce adjustments.
    """

    def analyze_compliance(self, week_plan) -> Dict:
        """
        Compare planned vs actual for a completed week.

        Args:
            week_plan: WeekPlan model instance with actual_* fields filled

        Returns:
            Dict with compliance metrics
        """
        if not week_plan.actual_tss:
            return {
                "tss_compliance": 0.0,
                "sessions_compliance": 0.0,
                "hours_compliance": 0.0,
                "was_recovery_week": False,
                "skipped": True,
            }

        tss_ratio = week_plan.actual_tss / week_plan.target_tss if week_plan.target_tss > 0 else 0
        sessions_ratio = (
            week_plan.actual_sessions / week_plan.target_sessions
            if week_plan.target_sessions > 0
            else 0
        )
        hours_ratio = (
            week_plan.actual_hours / week_plan.target_hours if week_plan.target_hours > 0 else 0
        )

        # Recovery week detection: TSS < 70% of recent average
        is_recovery = week_plan.target_tss < 300  # Simple heuristic, can be improved

        return {
            "tss_compliance": tss_ratio,
            "sessions_compliance": sessions_ratio,
            "hours_compliance": hours_ratio,
            "was_recovery_week": is_recovery,
            "skipped": False,
            "week_number": week_plan.week_number,
            "phase": week_plan.phase,
        }

    def calculate_adjustments(
        self,
        program,
        current_week_number: int,
        current_profile: Dict,
        recent_weeks: List,
    ) -> Dict:
        """
        Determine adjustments for the next week based on fatigue and compliance.

        Args:
            program: TrainingProgram model instance
            current_week_number: The week being planned
            current_profile: Dict with FTP, CTL, ATL, TSB
            recent_weeks: List of WeekPlan instances (last 3-4 weeks)

        Returns:
            Dict with adjustment multipliers and reasoning
        """
        adjustments = {
            "tss_multiplier": 1.0,
            "force_recovery": False,
            "reasons": [],
        }

        tsb = current_profile.get("tsb", 0)
        ctl = current_profile.get("ctl", 0)
        atl = current_profile.get("atl", 0)

        # Rule 1: Critical fatigue (TSB < -20)
        if tsb < -20:
            adjustments["force_recovery"] = True
            adjustments["tss_multiplier"] = 0.5
            adjustments["reasons"].append(
                f"TSB critically low ({tsb:.1f}), forcing recovery week to prevent overtraining"
            )
            return adjustments  # Early return, this overrides everything

        # Rule 2: High fatigue (TSB < -10)
        elif tsb < -10:
            adjustments["tss_multiplier"] *= 0.85
            adjustments["reasons"].append(f"TSB below -10 ({tsb:.1f}), reducing load by 15%")

        # Rule 3: Very fresh (TSB > 15)
        elif tsb > 15:
            adjustments["tss_multiplier"] *= 1.10
            adjustments["reasons"].append(
                f"TSB very positive ({tsb:.1f}), rider is fresh, increasing load by 10%"
            )

        # Rule 4: Chronic under-compliance
        if len(recent_weeks) >= 2:
            compliance_ratios = []
            for wk in recent_weeks:
                if wk.actual_tss and wk.target_tss:
                    compliance_ratios.append(wk.actual_tss / wk.target_tss)

            if compliance_ratios:
                avg_compliance = sum(compliance_ratios) / len(compliance_ratios)

                if avg_compliance < 0.70:
                    adjustments["tss_multiplier"] *= 0.80
                    adjustments["reasons"].append(
                        f"Chronic under-compliance ({avg_compliance:.0%} of planned TSS), "
                        "reducing targets to match actual capacity"
                    )
                elif avg_compliance > 1.20:
                    adjustments["tss_multiplier"] *= 1.05
                    adjustments["reasons"].append(
                        f"Consistently exceeding targets ({avg_compliance:.0%}), "
                        "slightly increasing load"
                    )

        # Rule 5: CTL ramp rate check (max 7 TSS/day is sustainable)
        if len(recent_weeks) >= 1:
            # Calculate CTL ramp from 7 days ago to now
            recent_week = recent_weeks[-1]
            if recent_week.actual_ctl:
                # Estimate CTL from 7 days before recent_week
                # (Simplified: assume it was close to the week before that)
                if len(recent_weeks) >= 2:
                    prev_ctl = recent_weeks[-2].actual_ctl or ctl - 7
                else:
                    prev_ctl = ctl - 10  # Guess

                ctl_ramp = (recent_week.actual_ctl - prev_ctl) / 7

                if ctl_ramp > 7:
                    adjustments["tss_multiplier"] *= 0.90
                    adjustments["reasons"].append(
                        f"CTL ramp too fast ({ctl_ramp:.1f} TSS/day, max recommended 7), backing off"
                    )

        # Rule 6: Prevent TSS from dropping below 0.4 or exceeding 1.5 (safety bounds)
        adjustments["tss_multiplier"] = max(0.4, min(1.5, adjustments["tss_multiplier"]))

        return adjustments

    def detect_overtraining_risk(self, current_profile: Dict, recent_weeks: List) -> Dict:
        """
        Detect signs of overtraining or excessive fatigue.

        Returns:
            Dict with risk_level ("none", "low", "medium", "high") and warnings
        """
        tsb = current_profile.get("tsb", 0)
        ctl = current_profile.get("ctl", 0)
        atl = current_profile.get("atl", 0)

        warnings = []
        risk_level = "none"

        # Check 1: TSB persistently negative
        if tsb < -20:
            risk_level = "high"
            warnings.append("TSB below -20, high risk of overtraining")
        elif tsb < -15:
            risk_level = "medium"
            warnings.append("TSB below -15, moderate fatigue accumulation")
        elif tsb < -10:
            risk_level = "low"
            warnings.append("TSB below -10, slight fatigue buildup")

        # Check 2: ATL >> CTL (acute load spiking)
        if atl > ctl * 1.3:
            if risk_level == "none":
                risk_level = "low"
            warnings.append("Acute load spiking relative to chronic fitness")

        # Check 3: Rapid CTL ramp
        if len(recent_weeks) >= 2:
            recent = recent_weeks[-1]
            prev = recent_weeks[-2]
            if recent.actual_ctl and prev.actual_ctl:
                weekly_ctl_gain = recent.actual_ctl - prev.actual_ctl
                if weekly_ctl_gain > 10:
                    if risk_level in ["none", "low"]:
                        risk_level = "medium"
                    warnings.append(f"CTL increased by {weekly_ctl_gain:.1f} in one week (>10 is aggressive)")

        return {"risk_level": risk_level, "warnings": warnings, "tsb": tsb, "ctl": ctl, "atl": atl}

    def recommend_recovery_week(self, program, current_week_number: int) -> bool:
        """
        Check if a recovery week should be scheduled based on periodization rules.

        Recovery weeks should happen every 3-4 weeks typically.

        Args:
            program: TrainingProgram model instance with week_plans loaded
            current_week_number: The week being planned

        Returns:
            bool: True if a recovery week is recommended
        """
        import json

        macro_plan = json.loads(program.macro_plan_json)
        week_targets = macro_plan.get("week_targets", [])

        # Check if this week was already designated as a recovery week in the macro plan
        for wt in week_targets:
            if wt["week"] == current_week_number:
                return wt.get("is_recovery", False)

        # Otherwise, check if it's been 3-4 weeks since last recovery
        # (Look backwards through completed weeks)
        weeks_since_recovery = 0
        for wk in reversed(program.week_plans):
            if wk.week_number >= current_week_number:
                continue  # Skip future weeks

            if wk.status == "completed":
                weeks_since_recovery += 1

                # Check if it was a recovery week (TSS < 70% of target or marked as recovery)
                if wk.target_tss < 300 or (wk.adaptation_notes and "recovery" in wk.adaptation_notes.lower()):
                    break  # Found last recovery week

        # Recommend recovery every 4 weeks
        return weeks_since_recovery >= 4

    def adjust_week_distribution(
        self, target_tss: float, sessions_per_week: int, zone_focus: List[str], current_profile: Dict
    ) -> List[Dict]:
        """
        Distribute weekly TSS across N sessions with proper sequencing.

        Args:
            target_tss: Total TSS for the week
            sessions_per_week: Number of sessions (e.g., 5)
            zone_focus: List of workout types for this phase (e.g., ["Sweet Spot", "Threshold"])
            current_profile: Dict with FTP, CTL, TSB

        Returns:
            List of workout specs: [{"workout_type": "Sweet Spot", "target_tss": 75, "target_duration": 90}, ...]
        """
        tsb = current_profile.get("tsb", 0)

        # Distribution strategy based on TSB and session count
        if sessions_per_week == 3:
            # 3 sessions: 1 hard, 1 moderate, 1 easy
            ratios = [0.40, 0.35, 0.25]  # Hard, moderate, easy
        elif sessions_per_week == 4:
            # 4 sessions: 2 hard, 1 moderate, 1 easy
            ratios = [0.35, 0.30, 0.20, 0.15]
        elif sessions_per_week == 5:
            # 5 sessions: 2 hard, 2 moderate, 1 easy
            ratios = [0.30, 0.25, 0.20, 0.15, 0.10]
        elif sessions_per_week >= 6:
            # 6+ sessions: 2 hard, 2 moderate, 2+ easy
            ratios = [0.25, 0.20, 0.18, 0.15, 0.12, 0.10]
        else:
            # Fallback: equal distribution
            ratios = [1.0 / sessions_per_week] * sessions_per_week

        # Assign workout types based on zone_focus and TSS ratios
        workouts = []
        for i, ratio in enumerate(ratios[:sessions_per_week]):
            workout_tss = target_tss * ratio

            # Assign type based on TSS (high TSS = hard workout from zone_focus, low TSS = recovery)
            if workout_tss > 70:
                # Hard workout - pick from zone_focus
                workout_type = zone_focus[i % len(zone_focus)] if zone_focus else "Sweet Spot"
            elif workout_tss > 40:
                # Moderate - Endurance or Tempo
                workout_type = "Endurance" if i % 2 == 0 else "Tempo"
            else:
                # Easy - Recovery
                workout_type = "Recovery"

            # Estimate duration (TSS = duration * IF^2 / 3600 * FTP, rough estimate)
            # For simplicity: assume IF ~0.75 for moderate, 0.55 for recovery, 0.85 for hard
            if workout_type == "Recovery":
                est_duration = int(workout_tss / 0.30)  # ~0.55 IF → IF^2 = 0.30
            elif workout_type in ["Endurance", "Tempo"]:
                est_duration = int(workout_tss / 0.56)  # ~0.75 IF → IF^2 = 0.56
            else:
                est_duration = int(workout_tss / 0.72)  # ~0.85 IF → IF^2 = 0.72

            # Clamp duration
            est_duration = max(45, min(180, est_duration))

            workouts.append({
                "day_index": i + 1,
                "workout_type": workout_type,
                "target_tss": round(workout_tss, 1),
                "target_duration": est_duration,
            })

        return workouts
