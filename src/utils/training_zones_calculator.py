"""
Training Zones Calculator - CP zones, TSS, IF calculations
These are mathematical tools for the agent to use
"""
from typing import Dict


def calculate_cp_zones(ftp: float) -> Dict[str, Dict[str, float]]:
    """
    Calculate Critical Power (CP) zones based on FTP.

    Based on "Training and Racing with a Power Meter" by Allen & Coggan.
    CP zones represent sustainable power for different durations.

    Args:
        ftp: Functional Threshold Power in watts

    Returns:
        Dict of CP zones with min/max watts and %FTP
    """
    zones = {
        "CP180": {  # 3-hour power (base endurance)
            "min_watts": ftp * 0.50,
            "max_watts": ftp * 0.65,
            "min_pct": 50,
            "max_pct": 65,
            "duration_min": 180,
            "description": "Active Recovery / Easy Endurance"
        },
        "CP90": {  # 90-minute power (tempo/endurance)
            "min_watts": ftp * 0.76,
            "max_watts": ftp * 0.87,
            "min_pct": 76,
            "max_pct": 87,
            "duration_min": 90,
            "description": "Tempo / Muscular Endurance"
        },
        "CP60": {  # 60-minute power (FTP / threshold)
            "min_watts": ftp * 0.95,
            "max_watts": ftp * 1.05,
            "min_pct": 95,
            "max_pct": 105,
            "duration_min": 60,
            "description": "Threshold / FTP"
        },
        "CP30": {  # 30-minute power (sweet spot / tempo high end)
            "min_watts": ftp * 0.88,
            "max_watts": ftp * 0.93,
            "min_pct": 88,
            "max_pct": 93,
            "duration_min": 30,
            "description": "Sweet Spot"
        },
        "CP12": {  # 12-minute power (VO2max low end)
            "min_watts": ftp * 1.06,
            "max_watts": ftp * 1.15,
            "min_pct": 106,
            "max_pct": 115,
            "duration_min": 12,
            "description": "VO2max"
        },
        "CP6": {  # 6-minute power (VO2max)
            "min_watts": ftp * 1.15,
            "max_watts": ftp * 1.20,
            "min_pct": 115,
            "max_pct": 120,
            "duration_min": 6,
            "description": "VO2max High"
        },
        "CP1": {  # 1-minute power (anaerobic capacity)
            "min_watts": ftp * 1.50,
            "max_watts": ftp * 1.80,
            "min_pct": 150,
            "max_pct": 180,
            "duration_min": 1,
            "description": "Anaerobic Capacity"
        },
        "CP0.2": {  # 12-second power (neuromuscular)
            "min_watts": ftp * 2.00,
            "max_watts": ftp * 3.00,
            "min_pct": 200,
            "max_pct": 300,
            "duration_min": 0.2,
            "description": "Neuromuscular / Sprint"
        },
    }

    return zones


def calculate_coggan_zones(ftp: float) -> Dict[str, Dict[str, float]]:
    """
    Calculate Coggan 7-zone training system.

    Based on "Training and Racing with a Power Meter" by Allen & Coggan.

    Args:
        ftp: Functional Threshold Power in watts

    Returns:
        Dict of zones 1-7 with power ranges
    """
    zones = {
        "Z1": {
            "name": "Active Recovery",
            "min_watts": 0,
            "max_watts": ftp * 0.55,
            "min_pct": 0,
            "max_pct": 55,
            "description": "Easy spinning, blood flow, recovery"
        },
        "Z2": {
            "name": "Endurance",
            "min_watts": ftp * 0.56,
            "max_watts": ftp * 0.75,
            "min_pct": 56,
            "max_pct": 75,
            "description": "Aerobic base building, fat oxidation"
        },
        "Z3": {
            "name": "Tempo",
            "min_watts": ftp * 0.76,
            "max_watts": ftp * 0.90,
            "min_pct": 76,
            "max_pct": 90,
            "description": "Moderate intensity, muscular endurance"
        },
        "Z4": {
            "name": "Lactate Threshold",
            "min_watts": ftp * 0.91,
            "max_watts": ftp * 1.05,
            "min_pct": 91,
            "max_pct": 105,
            "description": "FTP intervals, threshold training"
        },
        "Z5": {
            "name": "VO2max",
            "min_watts": ftp * 1.06,
            "max_watts": ftp * 1.20,
            "min_pct": 106,
            "max_pct": 120,
            "description": "Maximal aerobic power, hard intervals"
        },
        "Z6": {
            "name": "Anaerobic Capacity",
            "min_watts": ftp * 1.21,
            "max_watts": ftp * 1.50,
            "min_pct": 121,
            "max_pct": 150,
            "description": "Short, very hard efforts above VO2max"
        },
        "Z7": {
            "name": "Neuromuscular Power",
            "min_watts": ftp * 1.51,
            "max_watts": float('inf'),
            "min_pct": 151,
            "max_pct": float('inf'),
            "description": "Sprints, maximal power bursts"
        },
    }

    return zones


def calculate_tss(duration_seconds: int, normalized_power: float, ftp: float) -> float:
    """
    Calculate Training Stress Score (TSS).

    Formula from "Training and Racing with a Power Meter":
    TSS = (duration_sec × NP × IF) / (FTP × 3600) × 100

    where IF (Intensity Factor) = NP / FTP

    Args:
        duration_seconds: Workout duration in seconds
        normalized_power: Normalized Power (weighted average)
        ftp: Functional Threshold Power

    Returns:
        TSS value
    """
    if ftp == 0:
        return 0

    intensity_factor = normalized_power / ftp
    tss = (duration_seconds * normalized_power * intensity_factor) / (ftp * 3600) * 100

    return round(tss, 1)


def calculate_normalized_power(intervals: list) -> float:
    """
    Estimate Normalized Power from interval structure.

    Simplified estimation (true NP requires 30-second rolling average of 4th power).
    For workout planning, we estimate based on weighted average.

    Args:
        intervals: List of intervals with duration (sec) and power (fraction of FTP)

    Returns:
        Normalized Power as fraction of FTP
    """
    if not intervals:
        return 0

    total_weighted_power = 0
    total_duration = 0

    for interval in intervals:
        duration = interval.get("duration", 0)
        power = interval.get("power", 0)

        # Weight higher intensities more (simple power^2 weighting)
        weighted_power = (power ** 2) * duration
        total_weighted_power += weighted_power
        total_duration += duration

    if total_duration == 0:
        return 0

    # Normalized power is approximately sqrt of weighted average
    np = (total_weighted_power / total_duration) ** 0.5

    return round(np, 3)


def calculate_intensity_factor(normalized_power: float, ftp: float) -> float:
    """
    Calculate Intensity Factor (IF).

    IF = Normalized Power / FTP

    Args:
        normalized_power: Normalized Power in watts
        ftp: Functional Threshold Power in watts

    Returns:
        IF (typically 0.50 to 1.10)
    """
    if ftp == 0:
        return 0

    return round(normalized_power / ftp, 3)


def estimate_tss_from_structure(intervals: list, ftp: float) -> Dict[str, float]:
    """
    Estimate TSS, NP, and IF from workout structure.

    Args:
        intervals: List of intervals with duration (sec) and power (fraction of FTP)
        ftp: Functional Threshold Power in watts

    Returns:
        Dict with tss, normalized_power, intensity_factor
    """
    # Convert power fractions to watts
    intervals_watts = []
    total_duration = 0

    for interval in intervals:
        duration = interval.get("duration", 0)
        power_fraction = interval.get("power", 0)

        intervals_watts.append({
            "duration": duration,
            "power": power_fraction * ftp
        })
        total_duration += duration

    # Calculate NP
    np_watts = calculate_normalized_power([
        {"duration": i["duration"], "power": i["power"] / ftp}
        for i in intervals_watts
    ]) * ftp

    # Calculate IF
    intensity_factor = calculate_intensity_factor(np_watts, ftp)

    # Calculate TSS
    tss = calculate_tss(total_duration, np_watts, ftp)

    return {
        "tss": tss,
        "normalized_power": round(np_watts, 1),
        "intensity_factor": intensity_factor,
        "duration_minutes": round(total_duration / 60, 1)
    }


def get_workout_type_zones(workout_type: str, ftp: float) -> Dict[str, float]:
    """
    Get recommended power zones for a workout type.

    Args:
        workout_type: Type of workout (Recovery, Endurance, Tempo, Sweet Spot, etc.)
        ftp: Functional Threshold Power

    Returns:
        Dict with min_watts, max_watts, min_pct, max_pct
    """
    cp_zones = calculate_cp_zones(ftp)

    type_mapping = {
        "Recovery": {
            "min_watts": ftp * 0.50,
            "max_watts": ftp * 0.60,
            "min_pct": 50,
            "max_pct": 60,
            "cp_zone": "CP180 (low end)"
        },
        "Endurance": {
            "min_watts": ftp * 0.56,
            "max_watts": ftp * 0.75,
            "min_pct": 56,
            "max_pct": 75,
            "cp_zone": "CP180 / Z2"
        },
        "Tempo": {
            "min_watts": ftp * 0.76,
            "max_watts": ftp * 0.90,
            "min_pct": 76,
            "max_pct": 90,
            "cp_zone": "CP90 / Z3"
        },
        "Sweet Spot": {
            "min_watts": ftp * 0.88,
            "max_watts": ftp * 0.93,
            "min_pct": 88,
            "max_pct": 93,
            "cp_zone": "CP30 (88-93% FTP)"
        },
        "Threshold": {
            "min_watts": ftp * 0.94,
            "max_watts": ftp * 1.05,
            "min_pct": 94,
            "max_pct": 105,
            "cp_zone": "CP60 / Z4"
        },
        "VO2max": {
            "min_watts": ftp * 1.06,
            "max_watts": ftp * 1.20,
            "min_pct": 106,
            "max_pct": 120,
            "cp_zone": "CP6-CP12 / Z5"
        },
        "Anaerobic": {
            "min_watts": ftp * 1.20,
            "max_watts": ftp * 1.80,
            "min_pct": 120,
            "max_pct": 180,
            "cp_zone": "CP1 / Z6"
        },
        "Force": {
            "min_watts": ftp * 0.80,
            "max_watts": ftp * 0.92,
            "min_pct": 80,
            "max_pct": 92,
            "cp_zone": "CP30-CP90 (Muscular Endurance, low cadence 50-60rpm)"
        },
    }

    return type_mapping.get(workout_type, {
        "min_watts": ftp * 0.70,
        "max_watts": ftp * 0.80,
        "min_pct": 70,
        "max_pct": 80,
        "cp_zone": "Unknown"
    })


def format_zones_for_prompt(ftp: float) -> str:
    """
    Format power zones as a readable string for the agent's prompt.

    Args:
        ftp: Functional Threshold Power

    Returns:
        Formatted string with all zones
    """
    cp_zones = calculate_cp_zones(ftp)
    coggan_zones = calculate_coggan_zones(ftp)

    output = f"=== POWER ZONES FOR FTP = {ftp:.0f}W ===\n\n"

    output += "Critical Power (CP) Zones:\n"
    for zone_name, zone_data in sorted(cp_zones.items(),
                                       key=lambda x: x[1]['duration_min'],
                                       reverse=True):
        output += f"  {zone_name}: {zone_data['min_watts']:.0f}-{zone_data['max_watts']:.0f}W "
        output += f"({zone_data['min_pct']}-{zone_data['max_pct']}% FTP) - {zone_data['description']}\n"

    output += "\nCoggan 7-Zone System:\n"
    for zone_num in range(1, 8):
        zone_key = f"Z{zone_num}"
        zone_data = coggan_zones[zone_key]
        max_w = f"{zone_data['max_watts']:.0f}W" if zone_data['max_watts'] != float('inf') else "MAX"
        output += f"  {zone_key} ({zone_data['name']}): {zone_data['min_watts']:.0f}-{max_w} "
        output += f"({zone_data['min_pct']}-{zone_data['max_pct'] if zone_data['max_pct'] != float('inf') else 'MAX'}% FTP)\n"

    return output
