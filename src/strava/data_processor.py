"""
Process Strava activities and enrich with calculated metrics
"""
from typing import List, Dict, Any
from .metrics import TrainingMetrics
from .client import StravaDataClient


class StravaDataProcessor:
    """Process Strava activities and calculate metrics"""

    def __init__(self, ftp: float):
        """
        Initialize data processor

        Args:
            ftp: User's Functional Threshold Power
        """
        self.ftp = ftp
        self.metrics = TrainingMetrics()

    def process_activity(
        self, activity: Dict[str, Any], streams: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Process a single activity and calculate metrics

        Args:
            activity: Activity data from Strava
            streams: Optional power streams for detailed calculations

        Returns:
            Enriched activity with calculated metrics
        """
        # Calculate NP from streams if available, otherwise use weighted_average_watts
        if streams and streams.get("watts"):
            normalized_power = self.metrics.calculate_normalized_power(streams["watts"])
        else:
            # Fallback to weighted average or average watts
            normalized_power = activity.get("weighted_average_watts") or activity.get("average_watts")
            # Convert None to 0.0
            if normalized_power is None:
                normalized_power = 0.0

        # Calculate IF and TSS
        intensity_factor = self.metrics.calculate_intensity_factor(normalized_power, self.ftp)
        tss = self.metrics.calculate_tss(
            activity["moving_time"], normalized_power, intensity_factor, self.ftp
        )

        # Calculate zone distribution
        zone_distribution = {}
        if streams and streams.get("watts"):
            zone_distribution = self.metrics.calculate_zone_distribution(
                streams["watts"], self.ftp
            )

        # Enrich activity data
        processed = {
            **activity,
            "normalized_power": round(normalized_power, 1),
            "intensity_factor": round(intensity_factor, 3),
            "tss": round(tss, 1),
            **zone_distribution,
        }

        return processed

    def process_activities_batch(
        self,
        activities: List[Dict[str, Any]],
        fetch_streams: bool = False,
        client: StravaDataClient = None,
    ) -> List[Dict[str, Any]]:
        """
        Process multiple activities

        Args:
            activities: List of activities from Strava
            fetch_streams: Whether to fetch detailed power streams
            client: Strava client (required if fetch_streams=True)

        Returns:
            List of processed activities with metrics
        """
        processed_activities = []

        for i, activity in enumerate(activities):
            streams = None
            if fetch_streams and client:
                streams = client.get_activity_streams(activity["id"])
                # Rate limiting: Strava allows 100 requests per 15min, 1000 per day
                # Sleep 0.2s between stream requests (max 300 per minute = 5 per second)
                if i < len(activities) - 1:  # Don't sleep after last activity
                    import time
                    time.sleep(0.2)

            processed = self.process_activity(activity, streams)
            processed_activities.append(processed)

        return processed_activities
