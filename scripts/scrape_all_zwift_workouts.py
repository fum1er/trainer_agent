"""
Scrape ALL workouts from whatsonzwift.com (modern + legacy collections)
Comprehensive scraper that retrieves all available Zwift workouts
"""
import requests
from bs4 import BeautifulSoup
import time
import re
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.database import get_db
from src.database.models import ZwiftWorkout
from sqlalchemy.exc import IntegrityError


def get_all_workout_categories():
    """
    Get ALL workout categories from whatsonzwift.com/workouts
    Includes: Modern collections, Legacy collections, Training Plans

    Returns:
        List of category dicts with name and URL
    """
    print("Fetching workout categories...")

    url = "https://whatsonzwift.com/workouts/"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, 'html.parser')

    categories = []

    # Target sections
    section_names = [
        'Zwift workout collections',
        'Legacy Zwift workout collections',
        'Zwift training plans'  # Also get training plans
    ]

    for section_name in section_names:
        h2 = soup.find('h2', string=lambda x: x and section_name in x)
        if h2:
            section = h2.find_parent('section')
            if section:
                category_links = section.find_all('a', href=True)

                for link in category_links:
                    href = link.get('href', '')

                    if 'whatsonzwift.com/workouts/' in href and '#' not in href:
                        category_slug = href.split('/workouts/')[-1].strip('/')

                        if category_slug and href not in [c['url'] for c in categories]:
                            category_name = category_slug.replace('-', ' ').title()
                            full_url = href if href.startswith('http') else f"https://whatsonzwift.com{href}"

                            categories.append({
                                'name': category_name,
                                'url': full_url,
                                'section': section_name
                            })

    print(f"Found {len(categories)} categories")
    return categories


def scrape_workout_list_from_category(category_url):
    """Scrape all workout URLs from a category page"""
    print(f"  Scraping: {category_url}")

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    try:
        response = requests.get(category_url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"    Error fetching category: {e}")
        return []

    soup = BeautifulSoup(response.content, 'html.parser')
    workout_urls = []

    # Find h3 tags (workout names)
    workout_headers = soup.find_all('h3')

    for h3 in workout_headers:
        parent = h3.find_parent('header')
        if parent:
            links = parent.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                # Workout URLs have 5+ slashes
                if 'whatsonzwift.com/workouts/' in href and href.count('/') >= 5 and '#' not in href:
                    full_url = href if href.startswith('http') else f"https://whatsonzwift.com{href}"
                    if full_url not in workout_urls:
                        workout_urls.append(full_url)

    print(f"    Found {len(workout_urls)} workouts")
    return workout_urls


def parse_interval_structure(soup):
    """Parse interval structure from .textbar divs"""
    intervals = []
    textbar_divs = soup.select('.textbar')

    for div in textbar_divs:
        text = div.get_text(strip=True)

        # Parse duration (handle floats)
        duration_match = re.search(r'([\d.]+)\s*min', text, re.I)
        if duration_match:
            try:
                duration_seconds = int(float(duration_match.group(1)) * 60)
            except ValueError:
                continue
        else:
            duration_seconds = 0

        # Parse cadence
        cadence_match = re.search(r'@\s*(\d+)\s*rpm', text, re.I)
        cadence = int(cadence_match.group(1)) if cadence_match else None

        # Parse power
        power_spans = div.select('span[data-unit="relpow"]')

        if not power_spans:
            continue

        try:
            if len(power_spans) == 1:
                # Steady state
                power_value = int(power_spans[0].get('data-value', 0))
                intervals.append({
                    'type': 'SteadyState',
                    'duration': duration_seconds,
                    'power': power_value / 100.0,
                    'cadence': cadence,
                    'total_duration': duration_seconds
                })

            elif len(power_spans) == 2:
                # Ramp (warmup/cooldown)
                power_low = int(power_spans[0].get('data-value', 0))
                power_high = int(power_spans[1].get('data-value', 0))
                interval_type = 'Warmup' if power_low < power_high else 'Cooldown'

                intervals.append({
                    'type': interval_type,
                    'duration': duration_seconds,
                    'power_low': power_low / 100.0,
                    'power_high': power_high / 100.0,
                    'cadence': cadence,
                    'total_duration': duration_seconds
                })
        except (ValueError, TypeError) as e:
            # Skip invalid power values
            continue

    return intervals


def calculate_avg_power_from_intervals(intervals):
    """Calculate weighted average power"""
    total_power_time = 0
    total_time = 0

    for interval in intervals:
        duration = interval.get('total_duration', 0)

        if interval['type'] == 'SteadyState':
            power = interval.get('power', 0)
            total_power_time += duration * power
            total_time += duration
        elif interval['type'] in ['Warmup', 'Cooldown', 'Ramp']:
            power_avg = (interval.get('power_low', 0) + interval.get('power_high', 0)) / 2
            total_power_time += duration * power_avg
            total_time += duration

    return total_power_time / total_time if total_time > 0 else 0.65


def estimate_tss(duration_seconds, normalized_power_fraction):
    """Estimate TSS"""
    if_value = normalized_power_fraction
    tss = (duration_seconds / 3600) * if_value * if_value * 100
    return tss


def classify_workout_type(avg_power):
    """Classify based on average power"""
    if avg_power < 0.60:
        return "Recovery"
    elif avg_power < 0.75:
        return "Endurance"
    elif avg_power < 0.88:
        return "Tempo"
    elif avg_power < 0.93:
        return "Sweet Spot"
    elif avg_power < 1.05:
        return "Threshold"
    elif avg_power < 1.20:
        return "VO2max"
    else:
        return "Anaerobic"


def parse_workout_page(workout_url):
    """Parse a single workout page and extract all details"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    try:
        response = requests.get(workout_url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Extract workout name
        title_elem = soup.select_one('h1')
        workout_name = title_elem.get_text(strip=True) if title_elem else "Unknown Workout"

        # Extract description
        # Description is in a <p> tag after the workout overview div
        # It's typically in the order-1 sm:order-2 section
        description = ""

        # Try to find the description paragraph
        # It's usually after the workout overview section
        workout_section = soup.find('section')
        if workout_section:
            # Find all <p> tags in the section
            p_tags = workout_section.find_all('p')
            for p in p_tags:
                text = p.get_text(strip=True)
                # Description is usually a longer paragraph (not the short stats)
                # Skip paragraphs with "Duration", "Stress points", etc.
                if len(text) > 50 and 'Duration' not in text and 'Stress points' not in text and 'Strong' not in text:
                    description = text
                    break

        if not description:
            # Fallback: try standard selectors
            desc_elem = soup.select_one('.description, p.description')
            description = desc_elem.get_text(strip=True) if desc_elem else ""

        # Extract stats (Duration, TSS/Stress points, Zone distribution)
        stats = {}

        # Find Workout overview section
        overview_section = soup.find('h6', string=lambda x: x and 'Workout overview' in x)
        if overview_section and overview_section.parent:
            overview_p_tags = overview_section.parent.find_all('p')
            for p in overview_p_tags:
                text = p.get_text(strip=True)

                # Extract Duration (can be "55m" or "1h46" or "2h")
                if 'Duration' in text:
                    # Try hours format first: "1h46", "2h30", "1h"
                    duration_match = re.search(r'Duration:\s*(\d+h\d*)', text)
                    if not duration_match:
                        # Try minutes only: "55m"
                        duration_match = re.search(r'Duration:\s*(\d+m)', text)
                    if duration_match:
                        stats['duration'] = duration_match.group(1)

                # Extract TSS/Stress points
                if 'Stress points' in text:
                    tss_match = re.search(r'Stress points:\s*(\d+)', text)
                    if tss_match:
                        stats['tss'] = tss_match.group(1)

        # Find Zone distribution
        zone_distribution = {}
        zone_section = soup.find('h6', string=lambda x: x and 'Zone distribution' in x)
        if zone_section:
            # Find all <p> tags in the same parent
            parent = zone_section.parent
            if parent:
                zone_p_tags = parent.find_all('p')
                for p in zone_p_tags:
                    text = p.get_text(strip=True)
                    # Format: "Z1: 20m" or "Z5: -"
                    zone_match = re.search(r'(Z\d+):\s*(.+)', text)
                    if zone_match:
                        zone_distribution[zone_match.group(1)] = zone_match.group(2)

        stats['zone_distribution'] = zone_distribution

        # Parse intervals
        intervals = parse_interval_structure(soup)

        if not intervals:
            return None

        # Calculate metrics
        total_seconds = sum(i.get('total_duration', 0) for i in intervals)
        duration_minutes = total_seconds // 60
        avg_power = calculate_avg_power_from_intervals(intervals)

        # Use scraped TSS if available, otherwise calculate
        if stats.get('tss'):
            try:
                tss = int(stats['tss'])
            except ValueError:
                tss = int(estimate_tss(total_seconds, avg_power))
        else:
            tss = int(estimate_tss(total_seconds, avg_power))

        # Use scraped duration if available
        if stats.get('duration'):
            # Parse duration: can be "55m", "1h46", "2h30", "1h"
            duration_str = stats['duration']

            # Check for hours format
            hour_match = re.search(r'(\d+)h(\d*)', duration_str)
            if hour_match:
                hours = int(hour_match.group(1))
                minutes = int(hour_match.group(2)) if hour_match.group(2) else 0
                duration_minutes = hours * 60 + minutes
            else:
                # Minutes only
                minute_match = re.search(r'(\d+)m', duration_str)
                if minute_match:
                    duration_minutes = int(minute_match.group(1))

        intensity_factor = round(avg_power, 2)
        workout_type = classify_workout_type(avg_power)

        # Extract category from URL
        # e.g., https://whatsonzwift.com/workouts/30-minutes-to-burn/workout-1 -> 30-minutes-to-burn
        url_parts = workout_url.split('/workouts/')
        if len(url_parts) > 1:
            category_slug = url_parts[1].split('/')[0]
            category = category_slug.replace('-', ' ').title()
        else:
            category = "General"

        # Difficulty (1-5)
        if tss < 40:
            difficulty = 1
        elif tss < 60:
            difficulty = 2
        elif tss < 80:
            difficulty = 3
        elif tss < 100:
            difficulty = 4
        else:
            difficulty = 5

        # Build training focus from description and stats
        training_focus = f"{workout_type} workout"
        if description:
            training_focus = f"{workout_type}: {description}"

        # Build use cases from zone distribution
        use_cases = []
        if stats.get('zone_distribution'):
            zones = stats['zone_distribution']
            dominant_zones = []
            for z, time in zones.items():
                if time and time != '-':
                    # Parse time (can be "20m", "1h31", etc.)
                    try:
                        if 'h' in time:
                            hour_match = re.search(r'(\d+)h(\d*)', time)
                            if hour_match:
                                hours = int(hour_match.group(1))
                                minutes = int(hour_match.group(2)) if hour_match.group(2) else 0
                                total_minutes = hours * 60 + minutes
                            else:
                                continue
                        else:
                            total_minutes = int(time.replace('m', '').strip())

                        if total_minutes > 10:
                            dominant_zones.append(z)
                    except (ValueError, AttributeError):
                        continue

            if dominant_zones:
                use_cases.append(f"Focus zones: {', '.join(dominant_zones)}")

        return {
            'name': workout_name[:200],
            'author': None,
            'description': description,
            'workout_type': workout_type,
            'category': category,
            'difficulty_level': difficulty,
            'duration_minutes': duration_minutes,
            'tss': tss,
            'intensity_factor': intensity_factor,
            'structure_json': {
                'intervals': intervals,
                'stats': stats  # Include scraped stats
            },
            'zwo_xml': None,
            'training_focus': training_focus,
            'use_cases': ', '.join(use_cases) if use_cases else None,
            'source_url': workout_url,
            'tags': None,
        }

    except Exception as e:
        print(f"      Error parsing {workout_url}: {e}")
        return None


def insert_workouts_to_db(workout_records):
    """Insert parsed workouts into database"""
    print(f"\nInserting {len(workout_records)} workouts into database...")

    with get_db() as db:
        inserted = 0
        skipped = 0

        for record in workout_records:
            try:
                # Check if exists by URL
                existing = db.query(ZwiftWorkout).filter(
                    ZwiftWorkout.source_url == record['source_url']
                ).first()

                if existing:
                    skipped += 1
                    continue

                workout = ZwiftWorkout(**record)
                db.add(workout)
                db.commit()

                inserted += 1

                if inserted % 50 == 0:
                    print(f"  Inserted {inserted}...")

            except IntegrityError:
                db.rollback()
                skipped += 1
            except Exception as e:
                db.rollback()
                print(f"  Error inserting: {e}")

        print(f"\nDone!")
        print(f"  Inserted: {inserted}")
        print(f"  Skipped (duplicates): {skipped}")


def main():
    """Main scraping workflow"""
    print("=" * 60)
    print("WHATSONZWIFT.COM COMPREHENSIVE SCRAPER")
    print("=" * 60)

    # Step 1: Get all categories
    categories = get_all_workout_categories()

    if not categories:
        print("\nNo categories found. Exiting.")
        return

    print(f"\nScraping {len(categories)} categories...")

    all_workout_urls = []

    # Step 2: Get workout URLs from each category
    for i, cat in enumerate(categories, 1):
        print(f"\n[{i}/{len(categories)}] {cat['name']} ({cat['section']})")

        urls = scrape_workout_list_from_category(cat['url'])
        all_workout_urls.extend(urls)

        time.sleep(0.5)  # Be nice to the server

    workout_urls = list(set(all_workout_urls))  # Deduplicate

    print(f"\n{'='*60}")
    print(f"Found {len(workout_urls)} unique workouts")
    print(f"{'='*60}")

    # Step 3: Parse each workout
    print(f"\nParsing workout details...")

    workout_records = []

    for i, url in enumerate(workout_urls, 1):
        if i % 100 == 0:
            print(f"  Progress: {i}/{len(workout_urls)}")

        record = parse_workout_page(url)

        if record:
            workout_records.append(record)

        time.sleep(0.3)  # Be nice

    print(f"\nSuccessfully parsed {len(workout_records)} workouts")

    # Step 4: Insert to database
    if workout_records:
        insert_workouts_to_db(workout_records)

        # Show final stats
        print("\n" + "=" * 60)
        print("SCRAPING COMPLETE!")
        print("=" * 60)

        with get_db() as db:
            total = db.query(ZwiftWorkout).count()
            print(f"\nTotal workouts in database: {total}")

            # Sample by type
            print("\nSample workouts by type:")
            for wtype in ["Recovery", "Endurance", "Sweet Spot", "Threshold", "VO2max", "Anaerobic"]:
                sample = db.query(ZwiftWorkout).filter(ZwiftWorkout.workout_type == wtype).first()
                if sample:
                    print(f"  {wtype}: {sample.name} ({sample.duration_minutes}min, TSS {sample.tss})")
    else:
        print("\n❌ No workouts were successfully parsed")


if __name__ == "__main__":
    main()
