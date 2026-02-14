"""
Unit tests for database models
"""
import pytest
from src.database.database import init_db, get_db
from src.database.models import User, UserProfile, Activity


@pytest.fixture
def test_db():
    """Initialize test database"""
    init_db()
    yield
    # Cleanup if needed


def test_create_user(test_db):
    """Test user creation"""
    with get_db() as db:
        user = User(name="Test User", email="test@example.com")
        db.add(user)
        db.commit()

        assert user.id is not None


def test_create_user_profile(test_db):
    """Test user profile creation"""
    with get_db() as db:
        user = User(name="Test User", email="test2@example.com")
        db.add(user)
        db.commit()

        profile = UserProfile(user_id=user.id, ftp=265, weight=72)
        db.add(profile)
        db.commit()

        assert profile.ftp == 265
        assert profile.weight == 72


def test_create_activity(test_db):
    """Test activity creation"""
    from datetime import datetime

    with get_db() as db:
        user = User(name="Test User", email="test3@example.com")
        db.add(user)
        db.commit()

        activity = Activity(
            user_id=user.id,
            strava_activity_id="12345",
            name="Morning Ride",
            activity_type="Ride",
            start_date=datetime.now(),
            duration=3600,
            distance=30000,
            average_watts=200,
            tss=85.5,
        )
        db.add(activity)
        db.commit()

        assert activity.id is not None
        assert activity.tss == 85.5
