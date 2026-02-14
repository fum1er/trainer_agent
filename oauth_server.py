"""
Simple Flask server to handle Strava OAuth callback
Run this alongside Streamlit
"""
from flask import Flask, request, redirect
import webbrowser
from src.strava.auth import StravaAuth
from src.database.database import get_db
from src.database.models import User
import threading

app = Flask(__name__)
auth = StravaAuth()

@app.route('/strava_callback')
def strava_callback():
    """Handle OAuth callback from Strava"""
    code = request.args.get('code')

    if not code:
        return "Error: No code received", 400

    try:
        # Exchange code for tokens
        tokens = auth.exchange_code_for_token(code)

        # Store in database
        with get_db() as db:
            user = User(
                name="Strava User",
                strava_access_token=tokens["access_token"],
                strava_refresh_token=tokens["refresh_token"],
                strava_token_expires_at=tokens["expires_at"],
            )
            db.add(user)
            db.commit()
            user_id = user.id

        # Write success marker file for Streamlit to detect
        with open("data/.strava_connected", "w") as f:
            f.write(str(user_id))

        return """
        <html>
        <head><title>Success!</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1 style="color: green;">✓ Strava Connected!</h1>
            <p>You can close this window and return to Streamlit.</p>
            <p>Refresh the Streamlit page to continue.</p>
        </body>
        </html>
        """
    except Exception as e:
        return f"""
        <html>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h1 style="color: red;">Error</h1>
            <p>{str(e)}</p>
        </body>
        </html>
        """, 500

@app.route('/authorize')
def authorize():
    """Redirect to Strava authorization"""
    auth_url = auth.get_authorization_url()
    return redirect(auth_url)

def run_server():
    app.run(port=5000, debug=False)

if __name__ == "__main__":
    print("=" * 60)
    print("Strava OAuth Server Started")
    print("=" * 60)
    print("Server running on http://localhost:5000")
    print("To connect Strava, go to: http://localhost:5000/authorize")
    print("=" * 60)
    run_server()
