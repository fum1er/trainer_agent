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

            activities.append(
                {
                    "id": str(activity.id),
                    "name": activity.name,
                    "type": activity.type,
                    "start_date": activity.start_date,
                    "distance": float(activity.distance),
                    "moving_time": int(activity.moving_time.total_seconds()),
                    "elapsed_time": int(activity.elapsed_time.total_seconds()),
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

            return {
                "watts": streams.get("watts", {}).get("data", []),
                "time": streams.get("time", {}).get("data", []),
            }
        except Exception as e:
            print(f"Could not fetch streams for activity {activity_id}: {e}")
            return {"watts": [], "time": []}
