"""
SQLAlchemy models for Trainer Agent
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    """User account linked to Strava"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    strava_id = Column(String, unique=True, nullable=True)
    email = Column(String, unique=True, nullable=True)
    name = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    # OAuth tokens
    strava_access_token = Column(String, nullable=True)
    strava_refresh_token = Column(String, nullable=True)
    strava_token_expires_at = Column(DateTime, nullable=True)

    # Relationships
    profile = relationship("UserProfile", back_populates="user", uselist=False)
    activities = relationship("Activity", back_populates="user")
    preferences = relationship("UserPreference", back_populates="user", uselist=False)


class UserProfile(Base):
    """User's physical profile and training metrics"""

    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    # Physical attributes
    ftp = Column(Float, nullable=False)  # Watts
    weight = Column(Float, nullable=True)  # kg

    # Calculated zones (stored for quick access)
    zone1_max = Column(Float)  # 55% FTP
    zone2_max = Column(Float)  # 75% FTP
    zone3_max = Column(Float)  # 90% FTP
    zone4_max = Column(Float)  # 105% FTP
    zone5_max = Column(Float)  # 120% FTP
    zone6_max = Column(Float)  # 150% FTP

    # Training metrics (updated from Strava)
    ctl = Column(Float, default=0)  # Chronic Training Load
    atl = Column(Float, default=0)  # Acute Training Load
    tsb = Column(Float, default=0)  # Training Stress Balance

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="profile")


class UserPreference(Base):
    """User's training preferences and agent memory"""

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)

    # Training preferences
    typical_workout_duration = Column(Integer, default=90)  # minutes
    recovery_preference = Column(String, default="Moderate")  # Easy, Moderate, Hard

    # Agent memory
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="preferences")


class Activity(Base):
    """Cycling activity from Strava with calculated metrics"""

    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    # Strava data
    strava_activity_id = Column(String, unique=True)
    name = Column(String)
    activity_type = Column(String)  # Ride, VirtualRide
    start_date = Column(DateTime)

    # Metrics
    duration = Column(Integer)  # seconds
    distance = Column(Float)  # meters
    moving_time = Column(Integer)  # seconds

    # Power data
    average_watts = Column(Float, nullable=True)
    normalized_power = Column(Float, nullable=True)
    max_watts = Column(Float, nullable=True)

    # Calculated metrics
    tss = Column(Float, nullable=True)  # Training Stress Score
    intensity_factor = Column(Float, nullable=True)

    # Zone distribution (seconds in each zone)
    time_zone1 = Column(Integer, default=0)
    time_zone2 = Column(Integer, default=0)
    time_zone3 = Column(Integer, default=0)
    time_zone4 = Column(Integer, default=0)
    time_zone5 = Column(Integer, default=0)
    time_zone6 = Column(Integer, default=0)
    time_zone7 = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="activities")
