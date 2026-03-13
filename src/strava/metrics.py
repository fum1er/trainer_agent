"""
Training metrics calculations (TSS, CTL, ATL, TSB, zones)
"""
import numpy as np
from typing import List, Dict
from datetime import datetime, timedelta


class TrainingMetrics:
    """Calculate cycling training metrics"""

    @staticmethod
    def calculate_normalized_power(watts: List[float]) -> float:
        """
        Calculate Normalized Power (NP) from power data

        NP is the fourth root of the average of the fourth power
        of 30-second rolling average power

        Args:
            watts: List of power samples (1 per second)

        Returns:
            Normalized Power in watts
        """
        if not watts or len(watts) == 0:
            return 0.0

        # 30-second rolling average
        window = 30
        rolling_avg = np.convolve(watts, np.ones(window) / window, mode="valid")

        # Fourth power of rolling average
        fourth_power = np.power(rolling_avg, 4)

        # Average and take fourth root
        np_value = np.power(np.mean(fourth_power), 0.25)

        return float(np_value)

    @staticmethod
    def calculate_intensity_factor(normalized_power: float, ftp: float) -> float:
        """
        Calculate Intensity Factor (IF)

        IF = NP / FTP

        Args:
            normalized_power: Normalized Power
            ftp: Functional Threshold Power

        Returns:
            Intensity Factor
        """
        if not normalized_power or ftp == 0:
            return 0.0
        return normalized_power / ftp

    @staticmethod
    def calculate_tss(
        duration_seconds: int, normalized_power: float, intensity_factor: float, ftp: float
    ) -> float:
        """
        Calculate Training Stress Score (TSS)

        TSS = (duration_seconds × NP × IF) / (FTP × 3600) × 100

        Args:
            duration_seconds: Duration in seconds
            normalized_power: Normalized Power
            intensity_factor: Intensity Factor
            ftp: Functional Threshold Power

        Returns:
            Training Stress Score
        """
        if not normalized_power or not intensity_factor or ftp == 0:
            return 0.0

        tss = (duration_seconds * normalized_power * intensity_factor) / (ftp * 3600) * 100

        return float(tss)

    @staticmethod
    def calculate_zone_distribution(watts: List[float], ftp: float) -> Dict[str, int]:
        """
        Calculate time in each power zone (seconds)

        Zones:
        - Z1: <55% FTP (Recovery)
        - Z2: 56-75% FTP (Endurance)
        - Z3: 76-90% FTP (Tempo)
        - Z4: 91-105% FTP (Threshold)
        - Z5: 106-120% FTP (VO2max)
        - Z6: 121-150% FTP (Anaerobic)
        - Z7: >150% FTP (Neuromuscular)

        Args:
            watts: List of power samples (1 per second)
            ftp: Functional Threshold Power

        Returns:
            Dict with time_zone1 through time_zone7 (seconds)
        """
        # Zone boundaries (upper edges, exclusive); zone index = np.digitize result
        boundaries = [
            0.55 * ftp,   # Z1 < 55%
            0.75 * ftp,   # Z2 55-75%
            0.90 * ftp,   # Z3 75-90%
            1.05 * ftp,   # Z4 90-105%
            1.20 * ftp,   # Z5 105-120%
            1.50 * ftp,   # Z6 120-150%
        ]                 # Z7 > 150%

        watts_arr = np.asarray(watts)
        zone_indices = np.digitize(watts_arr, boundaries)  # returns 0-6 (maps to Z1-Z7)

        distribution = {f"time_zone{z}": 0 for z in range(1, 8)}
        for idx in range(7):
            distribution[f"time_zone{idx + 1}"] = int(np.sum(zone_indices == idx))

        return distribution

    @staticmethod
    def calculate_ctl_atl_tsb(
        activities_with_tss: List[Dict[str, any]], current_date: datetime = None
    ) -> Dict[str, float]:
        """
        Calculate CTL (42-day), ATL (7-day), and TSB

        CTL = Chronic Training Load (Fitness)
        ATL = Acute Training Load (Fatigue)
        TSB = Training Stress Balance (Form)

        Args:
            activities_with_tss: List of activities with start_date and tss
            current_date: Date to calculate for (default: now)

        Returns:
            Dict with ctl, atl, tsb
        """
        if current_date is None:
            current_date = datetime.now()

        # Sort activities by date
        sorted_activities = sorted(activities_with_tss, key=lambda x: x["start_date"])

        # Initialize
        ctl = 0.0  # Chronic Training Load (fitness)
        atl = 0.0  # Acute Training Load (fatigue)

        # CTL time constant (42 days)
        ctl_tc = 42
        # ATL time constant (7 days)
        atl_tc = 7

        # Calculate daily TSS
        daily_tss = {}
        for activity in sorted_activities:
            date = activity["start_date"].date()
            tss = activity.get("tss", 0)
            daily_tss[date] = daily_tss.get(date, 0) + tss

        # Calculate CTL and ATL
        start_date = current_date.date() - timedelta(days=90)  # Look back 90 days

        for i in range(90):
            date = start_date + timedelta(days=i)
            tss_today = daily_tss.get(date, 0)

            # Exponentially weighted moving average
            ctl = ctl + (tss_today - ctl) / ctl_tc
            atl = atl + (tss_today - atl) / atl_tc

        # TSB = CTL - ATL
        tsb = ctl - atl

        return {"ctl": round(ctl, 1), "atl": round(atl, 1), "tsb": round(tsb, 1)}
