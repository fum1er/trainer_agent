"""
Strava API client for fetching activities
"""
from stravalib.client import Client as StravaClient
from datetime import datetime, timedelta
from typing import List, Dict, Any
import time


class StravaDataClient:
    """Client for fetching data from Strava API"""

    def __init__(self, access_token: str):
        """
        Initialize Strava client

        Args:
            access_token: Strava OAuth access token
        """
        self.client = StravaClient(access_token=access_token)

    def get_athlete(self) -> Dict[str, Any]:
        """
        Get authenticated athlete information

        Returns:
            Dict with athlete data (id, name, weight, ftp)
        """
        athlete = self.client.get_athlete()
        return {
            "id": athlete.id,
            "firstname": athlete.firstname,
            "lastname": athlete.lastname,
            "weight": athlete.weight,
            "ftp": athlete.ftp if hasattr(athlete, "ftp") else None,
        }

    def get_athlete_stats(self, athlete_id: int = None) -> Dict[str, Any]:
        """
        Get athlete statistics including best power efforts

        Args:
            athlete_id: Athlete ID (if None, uses authenticated athlete)

        Returns:
            Dict with stats including best efforts (5s, 1min, 5min, 20min, etc.)
        """
        if athlete_id is None:
            athlete = self.client.get_athlete()
            athlete_id = athlete.id

        try:
            stats = self.client.get_athlete_stats(athlete_id)

            # Extract best power efforts from all time stats
            # Strava returns these in the "all_ride_totals" or recent totals
            best_efforts = {}

            # Check if power curve data is available
            # Note: This depends on having a power meter and activities with power data
            if hasattr(stats, 'recent_ride_totals'):
                # Recent totals include best efforts
                recent = stats.recent_ride_totals
                # Strava doesn't directly expose power curve in stats API
                # We'll need to calculate from activities instead

            return {
                "all_ride_totals": {
                    "count": stats.all_ride_totals.count if hasattr(stats, 'all_ride_totals') else 0,
                    "distance": stats.all_ride_totals.distance if hasattr(stats, 'all_ride_totals') else 0,
                    "elapsed_time": stats.all_ride_totals.elapsed_time if hasattr(stats, 'all_ride_totals') else 0,
                },
                "recent_ride_totals": {
                    "count": stats.recent_ride_totals.count if hasattr(stats, 'recent_ride_totals') else 0,
                    "distance": stats.recent_ride_totals.distance if hasattr(stats, 'recent_ride_totals') else 0,
                },
                "best_efforts": best_efforts,  # Will be populated from activities
            }
        except Exception as e:
            print(f"Warning: Could not fetch athlete stats: {e}")
            return {"best_efforts": {}}

    def get_activities(
        self, after: datetime = None, before: datetime = None, limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Fetch activities with rate limiting

        Args:
            after: Start date (default: 6 months ago)
            before: End date (default: now)
            limit: Max number of activities to fetch

        Returns:
            List of activity dicts
        """
        if after is None:
            # Default: last 6 months
            after = datetime.now() - timedelta(days=180)

        activities = []
        for activity in self.client.get_activities(after=after, before=before, limit=limit):
            # Rate limiting (Strava: 100 requests per 15 min, 1000 per day)
            time.sleep(0.1)

            # stravalib v2 uses Duration/Quantity objects, convert safely
            moving_time = activity.moving_time
            if hasattr(moving_time, 'total_seconds'):
                moving_time = int(moving_time.total_seconds())
            else:
                moving_time = int(moving_time)

            elapsed_time = activity.elapsed_time
            if hasattr(elapsed_time, 'total_seconds'):
                elapsed_time = int(elapsed_time.total_seconds())
            else:
                elapsed_time = int(elapsed_time)

            distance = activity.distance
            if hasattr(distance, 'magnitude'):
                distance = float(distance.magnitude)
            else:
                distance = float(distance) if distance else 0.0

            # Convert activity type to string (stravalib v2 uses RelaxedActivityType objects)
            activity_type = str(activity.type) if activity.type else "Unknown"

            activities.append(
                {
                    "id": str(activity.id),
                    "name": activity.name,
                    "type": activity_type,
                    "start_date": activity.start_date,
                    "distance": distance,
                    "moving_time": moving_time,
                    "elapsed_time": elapsed_time,
                    "average_watts": (
                        float(activity.average_watts) if activity.average_watts else None
                    ),
                    "max_watts": float(activity.max_watts) if activity.max_watts else None,
                    "weighted_average_watts": (
                        float(activity.weighted_average_watts)
                        if activity.weighted_average_watts
                        else None
                    ),
                }
            )

        return activities

    def get_activity_streams(self, activity_id: str) -> Dict[str, Any]:
        """
        Get power stream for zone distribution calculation

        Args:
            activity_id: Strava activity ID

        Returns:
            Dict with watts and time arrays
        """
        try:
            streams = self.client.get_activity_streams(
                activity_id, types=["watts", "time"], resolution="high"
            )

            # stravalib v2 returns Stream objects, not dicts
            # Access directly by attribute name or key
            watts_data = []
            time_data = []

            if streams:
                # Try both dict-style and attribute access for compatibility
                if hasattr(streams, 'get'):
                    # Dictionary-style access
                    watts_stream = streams.get("watts")
                    time_stream = streams.get("time")
                    if watts_stream:
                        watts_data = watts_stream.data if hasattr(watts_stream, 'data') else []
                    if time_stream:
                        time_data = time_stream.data if hasattr(time_stream, 'data') else []
                else:
                    # Attribute access (stravalib v2 style)
                    if hasattr(streams, 'watts') and streams.watts:
                        watts_data = streams.watts.data if hasattr(streams.watts, 'data') else []
                    if hasattr(streams, 'time') and streams.time:
                        time_data = streams.time.data if hasattr(streams.time, 'data') else []

            return {
                "watts": watts_data,
                "time": time_data,
            }
        except Exception as e:
            print(f"Could not fetch streams for activity {activity_id}: {e}")
            return {"watts": [], "time": []}
