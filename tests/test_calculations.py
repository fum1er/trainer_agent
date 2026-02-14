"""
Unit tests for training metrics calculations
"""
import pytest
from src.strava.metrics import TrainingMetrics


def test_normalized_power():
    """Test NP calculation"""
    watts = [200, 210, 205, 195, 200] * 60  # 5 minutes
    np = TrainingMetrics.calculate_normalized_power(watts)
    assert 195 < np < 210


def test_intensity_factor():
    """Test IF calculation"""
    np = 250
    ftp = 265
    if_val = TrainingMetrics.calculate_intensity_factor(np, ftp)
    assert 0.9 < if_val < 1.0
    assert round(if_val, 3) == 0.943


def test_tss():
    """Test TSS calculation"""
    duration = 3600  # 1 hour
    np = 250
    if_val = 0.943
    ftp = 265
    tss = TrainingMetrics.calculate_tss(duration, np, if_val, ftp)
    assert 80 < tss < 100


def test_zone_distribution():
    """Test power zone distribution"""
    watts = [100] * 60 + [200] * 60 + [300] * 60  # 1 min each in different zones
    ftp = 265
    zones = TrainingMetrics.calculate_zone_distribution(watts, ftp)

    # Check that we have time in multiple zones
    assert zones["time_zone1"] > 0  # 100W is in Z1 (<55% of 265 = <146W)
    assert zones["time_zone3"] > 0  # 200W is in Z3 (76-90% of 265 = 201-238W)
    assert zones["time_zone5"] > 0  # 300W is in Z5 (106-120% of 265 = 281-318W)


def test_ctl_atl_tsb():
    """Test CTL/ATL/TSB calculation"""
    from datetime import datetime, timedelta

    # Create mock activities
    activities = []
    base_date = datetime.now() - timedelta(days=30)
    for i in range(30):
        activities.append({"start_date": base_date + timedelta(days=i), "tss": 100})

    metrics = TrainingMetrics.calculate_ctl_atl_tsb(activities)

    assert "ctl" in metrics
    assert "atl" in metrics
    assert "tsb" in metrics
    assert metrics["ctl"] > 0
    assert metrics["atl"] > 0
