"""
.zwo file generator for Zwift/Wahoo compatibility
"""
import xml.etree.ElementTree as ET
from xml.dom import minidom


class ZwoGenerator:
    """Generate .zwo XML files for structured workouts"""

    def generate_zwo(self, name: str, description: str, intervals: list) -> str:
        """
        Generate complete .zwo file

        Args:
            name: Workout name
            description: Workout description
            intervals: List of interval dicts with type, duration, power

        Returns:
            XML string in .zwo format
        """
        root = ET.Element("workout_file")

        # Metadata
        ET.SubElement(root, "author").text = "Trainer Agent AI"
        ET.SubElement(root, "name").text = name
        ET.SubElement(root, "description").text = description
        ET.SubElement(root, "sportType").text = "bike"
        ET.SubElement(root, "tags")

        # Workout
        workout = ET.SubElement(root, "workout")

        # Add intervals
        for interval in intervals:
            if interval["type"] == "warmup":
                warmup_elem = ET.SubElement(
                    workout,
                    "Warmup",
                    Duration=str(interval["duration"]),
                    PowerLow=f"{interval['power_start']:.2f}",
                    PowerHigh=f"{interval['power_end']:.2f}",
                    pace="0"
                )
                # Add cadence if specified
                if "cadence" in interval:
                    warmup_elem.set("Cadence", str(interval["cadence"]))

            elif interval["type"] == "steadystate":
                steady_elem = ET.SubElement(
                    workout,
                    "SteadyState",
                    Duration=str(interval["duration"]),
                    Power=f"{interval['power']:.2f}",
                    pace="0"
                )
                # Add cadence if specified
                if "cadence" in interval:
                    steady_elem.set("Cadence", str(interval["cadence"]))

            elif interval["type"] == "intervals":
                interval_elem = ET.SubElement(
                    workout,
                    "IntervalsT",
                    Repeat=str(interval["repeat"]),
                    OnDuration=str(interval["on_duration"]),
                    OffDuration=str(interval["off_duration"]),
                    OnPower=f"{interval['on_power']:.2f}",
                    OffPower=f"{interval['off_power']:.2f}",
                    pace="0"
                )
                # Add cadence if specified (can have different cadence for on/off)
                if "cadence_on" in interval:
                    interval_elem.set("Cadence", str(interval["cadence_on"]))
                elif "cadence" in interval:
                    interval_elem.set("Cadence", str(interval["cadence"]))

                if "cadence_off" in interval:
                    interval_elem.set("CadenceResting", str(interval["cadence_off"]))

            elif interval["type"] == "cooldown":
                cooldown_elem = ET.SubElement(
                    workout,
                    "Cooldown",
                    Duration=str(interval["duration"]),
                    PowerLow=f"{interval['power_start']:.2f}",
                    PowerHigh=f"{interval['power_end']:.2f}",
                    pace="0"
                )
                # Add cadence if specified
                if "cadence" in interval:
                    cooldown_elem.set("Cadence", str(interval["cadence"]))

        # Pretty print XML
        rough_string = ET.tostring(root, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="    ")

        # Remove empty lines
        pretty_xml = "\n".join([line for line in pretty_xml.split("\n") if line.strip()])

        return pretty_xml

    def calculate_tss(self, intervals: list, ftp: float) -> float:
        """
        Estimate TSS from intervals

        Args:
            intervals: List of intervals
            ftp: Functional Threshold Power

        Returns:
            Estimated TSS
        """
        total_duration = 0
        weighted_power_sum = 0

        for interval in intervals:
            if interval["type"] == "warmup" or interval["type"] == "cooldown":
                duration = interval["duration"]
                avg_power = (interval["power_start"] + interval["power_end"]) / 2
                total_duration += duration
                weighted_power_sum += (avg_power * ftp) ** 4 * duration

            elif interval["type"] == "steadystate":
                duration = interval["duration"]
                power = interval["power"] * ftp
                total_duration += duration
                weighted_power_sum += power ** 4 * duration

            elif interval["type"] == "intervals":
                repeat = interval["repeat"]
                on_dur = interval["on_duration"]
                off_dur = interval["off_duration"]
                on_power = interval["on_power"] * ftp
                off_power = interval["off_power"] * ftp

                total_duration += (on_dur + off_dur) * repeat
                weighted_power_sum += (on_power ** 4 * on_dur + off_power ** 4 * off_dur) * repeat

        if total_duration == 0:
            return 0

        # Normalized Power
        np = (weighted_power_sum / total_duration) ** 0.25

        # Intensity Factor
        intensity_factor = np / ftp

        # TSS
        tss = (total_duration * np * intensity_factor) / (ftp * 36)

        return round(tss, 1)
