"""
TrainingPeaks API client — OAuth2 + planned workout upload.

Requires a TrainingPeaks developer account:
  https://help.trainingpeaks.com/hc/en-us/articles/360021403772

Set in .env:
  TRAININGPEAKS_CLIENT_ID=xxx
  TRAININGPEAKS_CLIENT_SECRET=xxx
"""
import logging
from datetime import datetime
from typing import Optional, Dict, List

import requests
from config import settings

logger = logging.getLogger(__name__)

_AUTH_URL = "https://api.trainingpeaks.com/OAuth/Authorize"
_TOKEN_URL = "https://api.trainingpeaks.com/OAuth/Token"
_API_BASE = "https://api.trainingpeaks.com/v1"

# Workout type IDs in TrainingPeaks
_WORKOUT_TYPE_IDS = {
    "Ride": 3,
    "VirtualRide": 3,
    "Run": 1,
    "Swim": 2,
}


class TrainingPeaksClient:
    """Thin wrapper around the TrainingPeaks REST API."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {access_token}"})

    # ── OAuth helpers (static) ─────────────────────────────────────────────
    @staticmethod
    def get_authorization_url(redirect_uri: Optional[str] = None) -> str:
        uri = redirect_uri or settings.trainingpeaks_redirect_uri
        client_id = settings.trainingpeaks_client_id
        scope = "workouts:write"
        return (
            f"{_AUTH_URL}?response_type=code"
            f"&client_id={client_id}"
            f"&redirect_uri={uri}"
            f"&scope={scope}"
        )

    @staticmethod
    def exchange_code_for_token(code: str) -> Dict:
        resp = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": settings.trainingpeaks_client_id,
                "client_secret": settings.trainingpeaks_client_secret,
                "redirect_uri": settings.trainingpeaks_redirect_uri,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def refresh_access_token(refresh_token: str) -> Dict:
        resp = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.trainingpeaks_client_id,
                "client_secret": settings.trainingpeaks_client_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Athlete ───────────────────────────────────────────────────────────
    def get_athlete(self) -> Dict:
        resp = self._session.get(f"{_API_BASE}/athlete/me", timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ── Planned Workouts ──────────────────────────────────────────────────
    def create_planned_workout(
        self,
        athlete_id: int,
        workout_date: datetime,
        title: str,
        description: str = "",
        planned_duration_seconds: int = 3600,
        planned_tss: float = 70,
        workout_type: str = "Ride",
        zwo_xml: Optional[str] = None,
    ) -> Dict:
        """
        Create a planned workout in TrainingPeaks.

        Returns the created workout dict from the API.
        """
        payload = {
            "athleteId": athlete_id,
            "workoutDay": workout_date.strftime("%Y-%m-%dT00:00:00"),
            "title": title,
            "workoutTypeValueId": _WORKOUT_TYPE_IDS.get(workout_type, 3),
            "coachNotes": description,
            "plannedDurationInSeconds": planned_duration_seconds,
            "plannedTss": planned_tss,
        }
        if zwo_xml:
            payload["structuredWorkoutContent"] = zwo_xml

        resp = self._session.post(
            f"{_API_BASE}/athlete/{athlete_id}/workouts",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def sync_program_to_trainingpeaks(
        self,
        athlete_id: int,
        planned_workouts: List[Dict],
        program_start_date: datetime,
    ) -> Dict:
        """
        Sync a list of planned workout dicts to TrainingPeaks.

        Each dict must have:
          - day_index: 1-based day offset from program_start_date
          - workout_type: str
          - target_tss: float
          - target_duration: int (minutes)
          - instructions: str (used as description)
          - name: str (optional)
          - zwo_xml: str (optional)

        Returns summary: {uploaded: int, failed: int, errors: list}
        """
        uploaded = 0
        failed = 0
        errors = []

        for pw in planned_workouts:
            try:
                workout_date = program_start_date + __import__("datetime").timedelta(
                    days=pw["day_index"] - 1
                )
                self.create_planned_workout(
                    athlete_id=athlete_id,
                    workout_date=workout_date,
                    title=pw.get("name") or pw["workout_type"],
                    description=pw.get("instructions", ""),
                    planned_duration_seconds=pw["target_duration"] * 60,
                    planned_tss=pw["target_tss"],
                    workout_type="VirtualRide",
                    zwo_xml=pw.get("zwo_xml"),
                )
                uploaded += 1
            except Exception as e:
                failed += 1
                errors.append(str(e))
                logger.error("TP upload failed for workout %s: %s", pw.get("name"), e)

        return {"uploaded": uploaded, "failed": failed, "errors": errors}

    def is_configured(self) -> bool:
        return bool(settings.trainingpeaks_client_id and settings.trainingpeaks_client_secret)
