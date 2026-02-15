"""
SQLAlchemy models for Trainer Agent
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, JSON
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
    programs = relationship("TrainingProgram", back_populates="user")


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

    # Power curve best efforts (last 3 months)
    best_5s = Column(Float, nullable=True)  # 5-second max power
    best_15s = Column(Float, nullable=True)  # 15-second max power
    best_30s = Column(Float, nullable=True)  # 30-second max power
    best_1min = Column(Float, nullable=True)  # 1-minute max power
    best_5min = Column(Float, nullable=True)  # 5-minute max power
    best_20min = Column(Float, nullable=True)  # 20-minute max power (FTP proxy)
    best_60min = Column(Float, nullable=True)  # 60-minute max power

    # Power curve all-time PRs
    pr_5s = Column(Float, nullable=True)
    pr_15s = Column(Float, nullable=True)
    pr_30s = Column(Float, nullable=True)
    pr_1min = Column(Float, nullable=True)
    pr_5min = Column(Float, nullable=True)
    pr_20min = Column(Float, nullable=True)
    pr_60min = Column(Float, nullable=True)

    # Rider profile analysis
    rider_type = Column(String, nullable=True)  # sprinter, puncheur, time_trialist, etc.
    power_profile_json = Column(Text, nullable=True)  # Full analysis JSON

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


class WorkoutPlan(Base):
    """Generated workout plans with structure and metadata"""

    __tablename__ = "workout_plans"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    # Workout metadata
    name = Column(String, nullable=False)
    workout_type = Column(String)  # Recovery, Endurance, Sweet Spot, Threshold, VO2max
    description = Column(Text)

    # Metrics
    target_duration = Column(Integer)  # minutes
    target_tss = Column(Float)
    intensity_factor = Column(Float)

    # Structure
    interval_structure = Column(Text)  # Human-readable structure
    zwo_xml = Column(Text)  # Full .zwo file content

    # Generation context
    user_request = Column(Text)  # Original user input
    agent_reasoning = Column(Text)  # Why this workout was chosen
    rag_context = Column(Text, nullable=True)  # Theory used

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User")
    feedback = relationship("WorkoutFeedback", back_populates="workout", uselist=False)


class WorkoutFeedback(Base):
    """User feedback on generated workouts for memory/adaptation"""

    __tablename__ = "workout_feedback"

    id = Column(Integer, primary_key=True)
    workout_id = Column(Integer, ForeignKey("workout_plans.id"), unique=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    # Rating
    rating = Column(Integer, nullable=True)  # 1-5 stars or thumbs up/down (1/5)

    # Feedback
    difficulty = Column(String, nullable=True)  # "too_easy", "perfect", "too_hard"
    notes = Column(Text, nullable=True)  # Freeform user comments
    workout_type = Column(String, nullable=True)  # Recovery, Endurance, Sweet Spot, Threshold, VO2max, etc.

    # Did they actually do it?
    completed = Column(Boolean, default=False)
    completion_date = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    workout = relationship("WorkoutPlan", back_populates="feedback")
    user = relationship("User")


class TrainingProgram(Base):
    """Long-term training program with periodization (multi-week plan)"""

    __tablename__ = "training_programs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))

    # Goal
    name = Column(String, nullable=False)  # "Road to 300W"
    goal_type = Column(String)  # "ftp_target", "race_prep", "base_building"
    goal_description = Column(Text)  # Free-text from user
    target_ftp = Column(Float, nullable=True)  # e.g. 300
    target_date = Column(DateTime, nullable=False)  # Deadline
    start_date = Column(DateTime, nullable=False)

    # Volume constraints
    hours_per_week = Column(Float, nullable=False)  # e.g. 10
    sessions_per_week = Column(Integer, nullable=False)  # e.g. 5

    # Macro plan (JSON blob - phases with week ranges, TSS targets, zone focus)
    macro_plan_json = Column(Text, nullable=False)  # Serialized JSON

    # Snapshot of rider state at plan creation
    initial_ftp = Column(Float)
    initial_ctl = Column(Float)

    # Status
    status = Column(String, default="active")  # active, completed, paused, cancelled

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="programs")
    week_plans = relationship("WeekPlan", back_populates="program", order_by="WeekPlan.week_number")


class WeekPlan(Base):
    """One week within a training program with planned vs actual tracking"""

    __tablename__ = "week_plans"

    id = Column(Integer, primary_key=True)
    program_id = Column(Integer, ForeignKey("training_programs.id"))
    week_number = Column(Integer, nullable=False)  # 1-indexed

    # Phase context
    phase = Column(String)  # "Base", "Build", "Peak", "Taper"

    # Planned targets (set by PlanAgent)
    target_tss = Column(Float)
    target_hours = Column(Float)
    target_sessions = Column(Integer)
    zone_focus = Column(String)  # "Endurance,Sweet Spot" - comma-separated
    week_instructions = Column(Text)  # Free-text coaching notes from PlanAgent

    # Actual results (filled after week is done, from Strava sync)
    actual_tss = Column(Float, nullable=True)
    actual_hours = Column(Float, nullable=True)
    actual_sessions = Column(Integer, nullable=True)
    actual_ctl = Column(Float, nullable=True)
    actual_atl = Column(Float, nullable=True)
    actual_tsb = Column(Float, nullable=True)

    # Adaptation notes (filled when PlanAgent re-plans)
    adaptation_notes = Column(Text, nullable=True)  # "Reduced TSS by 15% due to high fatigue"

    # Status
    status = Column(String, default="upcoming")  # upcoming, current, completed, skipped

    start_date = Column(DateTime)
    end_date = Column(DateTime)

    # Relationships
    program = relationship("TrainingProgram", back_populates="week_plans")
    planned_workouts = relationship("PlannedWorkout", back_populates="week_plan", order_by="PlannedWorkout.day_index")


class PlannedWorkout(Base):
    """Individual workout slot within a week, links to generated WorkoutPlan"""

    __tablename__ = "planned_workouts"

    id = Column(Integer, primary_key=True)
    week_plan_id = Column(Integer, ForeignKey("week_plans.id"))

    day_index = Column(Integer)  # 1-7 (Monday=1), or just sequence order
    workout_type = Column(String)  # "Sweet Spot", "VO2max", "Recovery", etc.
    target_tss = Column(Float)
    target_duration = Column(Integer)  # minutes
    instructions = Column(Text)  # Constraints to pass to WorkoutAgent

    # Link to actual generated workout (filled when user clicks "Generate")
    workout_plan_id = Column(Integer, ForeignKey("workout_plans.id"), nullable=True)

    # Link to actual Strava activity (matched after sync)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=True)

    # Status
    status = Column(String, default="planned")  # planned, generated, completed, skipped

    # Relationships
    week_plan = relationship("WeekPlan", back_populates="planned_workouts")
    workout_plan = relationship("WorkoutPlan")
    activity = relationship("Activity")


class ZwiftWorkout(Base):
    """
    Zwift workout library - structured workout data for fast SQL querying.

    Stores parsed Zwift workouts with metrics for filtering/sorting.
    Agent can query this table to find proven interval structures.
    """
    __tablename__ = "zwift_workouts"

    id = Column(Integer, primary_key=True)

    # Basic info
    name = Column(String, nullable=False, index=True)
    author = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    # Classification (indexed for fast filtering)
    workout_type = Column(String, nullable=False, index=True)  # VO2max, Threshold, Sweet Spot, etc.
    category = Column(String, nullable=True)  # Legacy, Academy, etc.
    difficulty_level = Column(Integer, nullable=True)  # 1-5

    # Metrics (for SQL queries: WHERE tss BETWEEN 60 AND 80)
    duration_minutes = Column(Integer, index=True)
    tss = Column(Integer, index=True)
    intensity_factor = Column(Float, index=True)

    # Interval structure as JSON (for agent to analyze)
    # Example: [{"type": "IntervalsT", "repeat": 3, "on_duration": 720, "on_power": 0.90, ...}]
    structure_json = Column(JSON, nullable=True)

    # Raw .zwo XML (in case we need to regenerate)
    zwo_xml = Column(Text, nullable=True)

    # Text descriptions (can optionally be indexed for RAG too)
    training_focus = Column(Text, nullable=True)  # "Aerobic power, lactate threshold"
    use_cases = Column(Text, nullable=True)  # "Build phase, 2-3x per week"

    # Metadata
    source_url = Column(String, nullable=True)
    tags = Column(String, nullable=True)  # Comma-separated tags

    created_at = Column(DateTime, default=datetime.utcnow)


class WorkoutTemplate(Base):
    """
    Generic workout templates from various sources (Zwift, TrainerRoad, custom).

    More abstract than ZwiftWorkout - represents workout patterns the agent can use.
    Agent queries this for inspiration when generating new workouts.
    """
    __tablename__ = "workout_templates"

    id = Column(Integer, primary_key=True)

    # Source tracking
    source = Column(String, nullable=False, index=True)  # "zwift", "trainerroad", "custom", "coach"
    source_id = Column(String, nullable=True)  # Original ID if from external source

    # Basic info
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Classification (indexed)
    workout_type = Column(String, nullable=False, index=True)
    difficulty_level = Column(Integer, nullable=True, index=True)  # 1-5

    # Metrics (for range queries)
    duration_minutes = Column(Integer, index=True)
    tss_range_min = Column(Integer, nullable=True)
    tss_range_max = Column(Integer, nullable=True)

    # Interval pattern (human-readable for agent)
    # Example: "3x12min@90%, 4min recovery" or "Pyramid: 2-3-4-5-4-3-2min@115%"
    interval_pattern = Column(Text, nullable=True)

    # Full structure as JSON
    structure_json = Column(JSON, nullable=True)

    # Tags for semantic search (JSON array)
    # Example: ["over-under", "progressive", "low-cadence", "force"]
    tags = Column(String, nullable=True)

    # Usage stats (for recommending popular templates)
    usage_count = Column(Integer, default=0)
    avg_rating = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
