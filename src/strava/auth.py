"""
Strava OAuth authentication
"""
from stravalib.client import Client
from config import settings
from datetime import datetime, timedelta


class StravaAuth:
    """Handle Strava OAuth flow"""

    def __init__(self):
        self.client_id = settings.strava_client_id
        self.client_secret = settings.strava_client_secret
        self.redirect_uri = settings.strava_redirect_uri

    def get_authorization_url(self) -> str:
        """
        Get Strava OAuth authorization URL

        Returns:
            Authorization URL for user to visit
        """
        client = Client()
        url = client.authorization_url(
            client_id=self.client_id,
            redirect_uri=self.redirect_uri,
            scope=["read", "activity:read_all", "profile:read_all"],
        )
        return url

    def exchange_code_for_token(self, code: str) -> dict:
        """
        Exchange authorization code for access token

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Dict with access_token, refresh_token, expires_at
        """
        client = Client()
        token_response = client.exchange_code_for_token(
            client_id=self.client_id, client_secret=self.client_secret, code=code
        )

        return {
            "access_token": token_response["access_token"],
            "refresh_token": token_response["refresh_token"],
            "expires_at": datetime.fromtimestamp(token_response["expires_at"]),
        }

    def refresh_access_token(self, refresh_token: str) -> dict:
        """
        Refresh expired access token

        Args:
            refresh_token: Refresh token from previous OAuth

        Returns:
            Dict with new access_token, refresh_token, expires_at
        """
        client = Client()
        token_response = client.refresh_access_token(
            client_id=self.client_id,
            client_secret=self.client_secret,
            refresh_token=refresh_token,
        )

        return {
            "access_token": token_response["access_token"],
            "refresh_token": token_response["refresh_token"],
            "expires_at": datetime.fromtimestamp(token_response["expires_at"]),
        }
