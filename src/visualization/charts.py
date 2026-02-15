"""
Plotly charts for training visualization
"""
import plotly.graph_objects as go
import plotly.express as px
from typing import List, Dict
import pandas as pd
from datetime import datetime, timedelta
import numpy as np


def create_pmc_chart(activities: List[Dict]) -> go.Figure:
    """
    Create Performance Management Chart (CTL/ATL/TSB)

    Args:
        activities: List of activities with date and TSS

    Returns:
        Plotly figure
    """
    if not activities:
        return go.Figure()

    # Create dataframe
    df = pd.DataFrame(activities)
    df['date'] = pd.to_datetime(df['start_date'])
    df = df.sort_values('date')

    # Calculate CTL (42-day exponential weighted average)
    df['ctl'] = df['tss'].ewm(span=42, adjust=False).mean()

    # Calculate ATL (7-day exponential weighted average)
    df['atl'] = df['tss'].ewm(span=7, adjust=False).mean()

    # Calculate TSB
    df['tsb'] = df['ctl'] - df['atl']

    # Create figure
    fig = go.Figure()

    # Add CTL line
    fig.add_trace(go.Scatter(
        x=df['date'],
        y=df['ctl'],
        name='CTL (Fitness)',
        line=dict(color='blue', width=2),
        hovertemplate='<b>CTL</b>: %{y:.1f}<br>%{x}<extra></extra>'
    ))

    # Add ATL line
    fig.add_trace(go.Scatter(
        x=df['date'],
        y=df['atl'],
        name='ATL (Fatigue)',
        line=dict(color='red', width=2),
        hovertemplate='<b>ATL</b>: %{y:.1f}<br>%{x}<extra></extra>'
    ))

    # Add TSB line
    fig.add_trace(go.Scatter(
        x=df['date'],
        y=df['tsb'],
        name='TSB (Form)',
        line=dict(color='green', width=2),
        fill='tozeroy',
        fillcolor='rgba(0,255,0,0.1)',
        hovertemplate='<b>TSB</b>: %{y:.1f}<br>%{x}<extra></extra>'
    ))

    # Add optimal training zone
    fig.add_hrect(
        y0=-10, y1=5,
        fillcolor="lightblue", opacity=0.1,
        layer="below", line_width=0,
        annotation_text="Optimal Training Zone",
        annotation_position="top left"
    )

    fig.update_layout(
        title="Performance Management Chart (Last 90 Days)",
        xaxis_title="Date",
        yaxis_title="Training Load",
        hovermode='x unified',
        template='plotly_white',
        height=500,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        )
    )

    return fig


def create_weekly_tss_chart(activities: List[Dict]) -> go.Figure:
    """
    Create weekly TSS bar chart

    Args:
        activities: List of activities

    Returns:
        Plotly figure
    """
    if not activities:
        return go.Figure()

    df = pd.DataFrame(activities)
    df['date'] = pd.to_datetime(df['start_date'])
    df['week'] = df['date'].dt.to_period('W').apply(lambda r: r.start_time)

    weekly_tss = df.groupby('week')['tss'].sum().reset_index()

    fig = go.Figure(data=[
        go.Bar(
            x=weekly_tss['week'],
            y=weekly_tss['tss'],
            marker_color='steelblue',
            hovertemplate='<b>Week</b>: %{x}<br><b>TSS</b>: %{y:.0f}<extra></extra>'
        )
    ])

    fig.update_layout(
        title="Weekly Training Stress Score",
        xaxis_title="Week",
        yaxis_title="TSS",
        template='plotly_white',
        height=400
    )

    return fig


def create_zone_distribution_chart(activities: List[Dict]) -> go.Figure:
    """
    Create zone distribution pie chart

    Args:
        activities: List of activities with zone times

    Returns:
        Plotly figure
    """
    if not activities:
        return go.Figure()

    df = pd.DataFrame(activities)

    # Sum time in each zone (convert seconds to hours)
    zone_columns = ['time_zone1', 'time_zone2', 'time_zone3', 'time_zone4', 'time_zone5', 'time_zone6', 'time_zone7']
    zone_times = []
    for col in zone_columns:
        if col in df.columns:
            zone_times.append(df[col].sum() / 3600)  # Convert to hours
        else:
            zone_times.append(0)

    # Check if we have any zone data
    total_zone_time = sum(zone_times)
    if total_zone_time == 0:
        # No zone data - show message
        fig = go.Figure()
        fig.add_annotation(
            text="No power zone data available<br>Zone distribution requires power meter data",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )
        fig.update_layout(
            title="Power Zone Distribution",
            template='plotly_white',
            height=400,
            xaxis=dict(visible=False),
            yaxis=dict(visible=False)
        )
        return fig

    zone_labels = ['Z1 Recovery', 'Z2 Endurance', 'Z3 Tempo', 'Z4 Threshold', 'Z5 VO2max', 'Z6 Anaerobic', 'Z7 Neuromuscular']
    colors = ['#90EE90', '#87CEEB', '#FFD700', '#FFA500', '#FF6347', '#DC143C', '#8B0000']

    fig = go.Figure(data=[go.Pie(
        labels=zone_labels,
        values=zone_times,
        marker=dict(colors=colors),
        hovertemplate='<b>%{label}</b><br>%{value:.1f} hours<br>%{percent}<extra></extra>'
    )])

    fig.update_layout(
        title="Power Zone Distribution",
        template='plotly_white',
        height=400
    )

    return fig


def create_power_curve(activities: List[Dict]) -> go.Figure:
    """
    Create power curve (best efforts)

    Args:
        activities: List of activities with power data

    Returns:
        Plotly figure
    """
    # For now, placeholder - would need actual power streams
    # This is a simplified version
    durations = [5, 60, 300, 1200, 3600]  # 5s, 1min, 5min, 20min, 60min
    duration_labels = ['5s', '1min', '5min', '20min', '60min']

    # Placeholder values - in real version, calculate from streams
    best_powers = [800, 500, 400, 300, 250]

    fig = go.Figure(data=[
        go.Scatter(
            x=duration_labels,
            y=best_powers,
            mode='lines+markers',
            line=dict(color='purple', width=3),
            marker=dict(size=10),
            hovertemplate='<b>%{x}</b><br>%{y:.0f}W<extra></extra>'
        )
    ])

    fig.update_layout(
        title="Power Curve (Best Efforts)",
        xaxis_title="Duration",
        yaxis_title="Power (W)",
        template='plotly_white',
        height=400
    )

    return fig


def create_program_timeline(macro_plan_json: Dict) -> go.Figure:
    """
    Create horizontal timeline showing training program phases

    Args:
        macro_plan_json: Dict with phases and weeks

    Returns:
        Plotly figure with phase timeline
    """
    if not macro_plan_json or "phases" not in macro_plan_json:
        return go.Figure()

    phases = macro_plan_json["phases"]

    # Phase colors
    phase_colors = {
        "Base": "#87CEEB",
        "Build": "#FFA500",
        "Peak": "#DC143C",
        "Taper": "#90EE90",
    }

    fig = go.Figure()

    for phase in phases:
        name = phase["name"]
        start_week = phase["weeks"][0]
        end_week = phase["weeks"][1]
        duration = end_week - start_week + 1

        fig.add_trace(go.Bar(
            name=name,
            y=["Training Program"],
            x=[duration],
            orientation='h',
            marker=dict(color=phase_colors.get(name, "#808080")),
            text=f"{name}<br>{duration} weeks",
            textposition='inside',
            hovertemplate=f'<b>{name}</b><br>Weeks {start_week}-{end_week}<br>{duration} weeks<extra></extra>',
            base=start_week - 1,  # Offset to start at correct week
        ))

    fig.update_layout(
        title="Training Program Phases",
        xaxis_title="Week",
        barmode='stack',
        template='plotly_white',
        height=200,
        showlegend=False,
        yaxis=dict(visible=False),
    )

    return fig


def create_planned_vs_actual_tss(week_plans: List) -> go.Figure:
    """
    Create grouped bar chart comparing planned vs actual TSS per week

    Args:
        week_plans: List of WeekPlan model instances

    Returns:
        Plotly figure
    """
    if not week_plans:
        return go.Figure()

    # Extract data
    weeks = []
    planned_tss = []
    actual_tss = []
    phases = []

    for wp in week_plans:
        weeks.append(f"W{wp.week_number}")
        planned_tss.append(wp.target_tss)
        actual_tss.append(wp.actual_tss if wp.actual_tss else 0)
        phases.append(wp.phase)

    # Phase colors for bars
    phase_colors = {
        "Base": "#87CEEB",
        "Build": "#FFA500",
        "Peak": "#DC143C",
        "Taper": "#90EE90",
    }

    # Map phase colors to each week
    bar_colors_planned = [phase_colors.get(p, "#808080") for p in phases]
    bar_colors_actual = [phase_colors.get(p, "#808080") for p in phases]

    fig = go.Figure()

    # Planned TSS (outlined bars)
    fig.add_trace(go.Bar(
        name='Planned TSS',
        x=weeks,
        y=planned_tss,
        marker=dict(
            color='rgba(255,255,255,0)',
            line=dict(color='gray', width=2),
        ),
        hovertemplate='<b>Planned</b><br>%{y:.0f} TSS<extra></extra>',
    ))

    # Actual TSS (filled bars)
    fig.add_trace(go.Bar(
        name='Actual TSS',
        x=weeks,
        y=actual_tss,
        marker=dict(color=bar_colors_actual),
        hovertemplate='<b>Actual</b><br>%{y:.0f} TSS<extra></extra>',
    ))

    fig.update_layout(
        title="Weekly TSS: Planned vs Actual",
        xaxis_title="Week",
        yaxis_title="TSS",
        barmode='overlay',
        template='plotly_white',
        height=400,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
    )

    return fig


def create_program_progress_chart(program, week_plans: List) -> go.Figure:
    """
    Create line chart showing CTL progression (projected vs actual)

    Args:
        program: TrainingProgram model instance
        week_plans: List of WeekPlan instances

    Returns:
        Plotly figure
    """
    import json

    if not week_plans:
        return go.Figure()

    macro_plan = json.loads(program.macro_plan_json)
    week_targets = macro_plan.get("week_targets", [])

    # Build data for chart
    weeks = []
    projected_ctl = []
    actual_ctl = []

    initial_ctl = program.initial_ctl or 50

    for i, wt in enumerate(week_targets):
        week_num = wt["week"]
        weeks.append(f"W{week_num}")

        # Projected CTL (simplified calculation: CTL grows with TSS)
        # CTL ≈ exponential weighted average with decay constant 42 days
        # Simplified: CTL increases by ~TSS/7 per week
        if i == 0:
            proj_ctl = initial_ctl + (wt["tss"] / 7)
        else:
            prev_ctl = projected_ctl[-1]
            proj_ctl = prev_ctl * 0.93 + wt["tss"] / 7  # Exponential decay + new load
        projected_ctl.append(proj_ctl)

        # Actual CTL from week_plans
        wp = next((w for w in week_plans if w.week_number == week_num), None)
        if wp and wp.actual_ctl:
            actual_ctl.append(wp.actual_ctl)
        else:
            actual_ctl.append(None)  # Future weeks or no data

    fig = go.Figure()

    # Projected CTL line
    fig.add_trace(go.Scatter(
        x=weeks,
        y=projected_ctl,
        name='Projected CTL',
        line=dict(color='blue', width=2, dash='dash'),
        hovertemplate='<b>Projected CTL</b>: %{y:.1f}<extra></extra>',
    ))

    # Actual CTL line (only for completed weeks)
    fig.add_trace(go.Scatter(
        x=weeks,
        y=actual_ctl,
        name='Actual CTL',
        line=dict(color='green', width=3),
        mode='lines+markers',
        hovertemplate='<b>Actual CTL</b>: %{y:.1f}<extra></extra>',
    ))

    fig.update_layout(
        title="Fitness (CTL) Progression",
        xaxis_title="Week",
        yaxis_title="CTL (Chronic Training Load)",
        template='plotly_white',
        height=400,
        hovermode='x unified',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1
        ),
    )

    return fig


def create_workout_profile_chart(intervals: list, ftp: float = 250) -> go.Figure:
    """
    Create a workout power profile chart showing intervals over time
    with colored zone bands and an FTP dashed line.

    Args:
        intervals: List of parsed interval dicts from WorkoutAgent._parse_intervals()
            Each has type (warmup/steadystate/intervals/cooldown) + power/duration
        ftp: Rider's FTP in watts

    Returns:
        Plotly figure with the workout profile
    """
    if not intervals:
        fig = go.Figure()
        fig.add_annotation(
            text="No workout structure available",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="gray"),
        )
        fig.update_layout(height=350, template="plotly_white")
        return fig

    # Zone definitions (% of FTP) with colors
    zones = [
        {"name": "Z1 Recovery", "low": 0.00, "high": 0.55, "color": "rgba(144,238,144,0.20)"},
        {"name": "Z2 Endurance", "low": 0.55, "high": 0.75, "color": "rgba(135,206,235,0.20)"},
        {"name": "Z3 Tempo", "low": 0.75, "high": 0.90, "color": "rgba(255,215,0,0.20)"},
        {"name": "Z4 Threshold", "low": 0.90, "high": 1.05, "color": "rgba(255,165,0,0.25)"},
        {"name": "Z5 VO2max", "low": 1.05, "high": 1.20, "color": "rgba(255,99,71,0.25)"},
        {"name": "Z6 Anaerobic", "low": 1.20, "high": 1.50, "color": "rgba(220,20,60,0.20)"},
        {"name": "Z7 Neuro", "low": 1.50, "high": 2.00, "color": "rgba(139,0,0,0.20)"},
    ]

    # Build time segments: (time_start_sec, time_end_sec, power_pct)
    segments = []
    t = 0

    for iv in intervals:
        iv_type = iv.get("type", "")

        if iv_type in ("warmup", "cooldown"):
            dur = iv["duration"]
            steps = max(1, dur // 15)
            step_dur = dur / steps
            p_start = iv["power_start"]
            p_end = iv["power_end"]
            for i in range(steps):
                p = p_start + (p_end - p_start) * (i + 0.5) / steps
                segments.append((t, t + step_dur, p))
                t += step_dur

        elif iv_type == "steadystate":
            segments.append((t, t + iv["duration"], iv["power"]))
            t += iv["duration"]

        elif iv_type == "intervals":
            repeat = iv.get("repeat", 1)
            for _ in range(repeat):
                segments.append((t, t + iv["on_duration"], iv["on_power"]))
                t += iv["on_duration"]
                segments.append((t, t + iv["off_duration"], iv["off_power"]))
                t += iv["off_duration"]

    if not segments:
        fig = go.Figure()
        fig.update_layout(height=350, template="plotly_white")
        return fig

    total_duration = t
    max_power_pct = max(s[2] for s in segments)
    y_max = max(max_power_pct + 0.10, 1.15)

    fig = go.Figure()

    # Zone background bands + labels
    for zone in zones:
        if zone["low"] < y_max:
            fig.add_hrect(
                y0=zone["low"] * ftp,
                y1=min(zone["high"], y_max + 0.05) * ftp,
                fillcolor=zone["color"], layer="below", line_width=0,
            )
            label_y = (zone["low"] + min(zone["high"], y_max)) / 2 * ftp
            fig.add_annotation(
                x=total_duration / 60, y=label_y,
                text=zone["name"], showarrow=False,
                font=dict(size=9, color="gray"),
                xanchor="left", xshift=5,
            )

    # FTP dashed line
    fig.add_hline(
        y=ftp, line_dash="dash", line_color="red", line_width=1.5,
        annotation_text=f"FTP {ftp:.0f}W",
        annotation_position="top left",
        annotation_font=dict(size=10, color="red"),
    )

    # Zone color mapping
    def _zone_color(power_pct):
        if power_pct <= 0.55:
            return "#90EE90"
        elif power_pct <= 0.75:
            return "#87CEEB"
        elif power_pct <= 0.90:
            return "#FFD700"
        elif power_pct <= 1.05:
            return "#FFA500"
        elif power_pct <= 1.20:
            return "#FF6347"
        elif power_pct <= 1.50:
            return "#DC143C"
        return "#8B0000"

    # Draw each segment as a colored filled polygon
    for start, end, power_pct in segments:
        watts = power_pct * ftp
        color = _zone_color(power_pct)
        fig.add_trace(go.Scatter(
            x=[start / 60, start / 60, end / 60, end / 60, start / 60],
            y=[0, watts, watts, 0, 0],
            fill="toself",
            fillcolor=color,
            line=dict(color=color, width=0.5),
            mode="lines",
            showlegend=False,
            hovertemplate=(
                f"<b>{power_pct*100:.0f}% FTP</b> ({watts:.0f}W)<br>"
                f"Duration: {(end-start)/60:.1f}min<extra></extra>"
            ),
        ))

    fig.update_layout(
        title="Workout Power Profile",
        xaxis_title="Time (min)",
        yaxis_title="Power (W)",
        template="plotly_white",
        height=380,
        margin=dict(r=80),
        xaxis=dict(range=[0, total_duration / 60 * 1.02]),
        yaxis=dict(range=[0, y_max * ftp]),
        hovermode="x",
    )

    return fig


def create_power_curve_spider_chart(power_curve: Dict[str, float], percentiles: Dict[str, float], rider_type: str) -> go.Figure:
    """
    Create spider/radar chart showing rider's power curve vs reference

    Args:
        power_curve: Dict of duration -> watts (e.g. {"5s": 1200, "1min": 400})
        percentiles: Dict of duration -> percentile vs reference (e.g. {"5s": 95, "1min": 85})
        rider_type: Classification (sprinter, puncheur, rouleur, climber, etc.)

    Returns:
        Plotly figure with radar chart
    """
    if not percentiles:
        fig = go.Figure()
        fig.add_annotation(
            text="No power curve data available",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="gray"),
        )
        fig.update_layout(height=400, template="plotly_white")
        return fig

    # Durations in order for radar chart
    durations = ["5s", "15s", "30s", "1min", "5min", "20min", "60min"]
    duration_labels = {
        "5s": "Sprint (5s)",
        "15s": "Anaerobic (15s)",
        "30s": "Anaerobic (30s)",
        "1min": "VO2 (1min)",
        "5min": "VO2max (5min)",
        "20min": "FTP (20min)",
        "60min": "Endurance (60min)",
    }

    # Extract values
    categories = [duration_labels.get(d, d) for d in durations]
    values = [percentiles.get(d, 0) for d in durations]
    powers = [power_curve.get(d, 0) for d in durations]

    # Close the loop for radar chart
    categories_closed = categories + [categories[0]]
    values_closed = values + [values[0]]

    fig = go.Figure()

    # Add rider's profile
    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=categories_closed,
        fill='toself',
        fillcolor='rgba(135,206,235,0.3)',
        line=dict(color='#1f77b4', width=2),
        name='Your Profile',
        hovertemplate='<b>%{theta}</b><br>%{r:.0f}% of reference<extra></extra>',
    ))

    # Add reference line at 100%
    reference_values = [100] * len(categories_closed)
    fig.add_trace(go.Scatterpolar(
        r=reference_values,
        theta=categories_closed,
        line=dict(color='red', width=2, dash='dash'),
        name='Cat 1/2 Reference',
        hovertemplate='<b>%{theta}</b><br>100% (reference)<extra></extra>',
    ))

    # Title with rider type
    rider_type_display = rider_type.replace("_", " ").title()
    title_text = f"Power Profile Analysis - {rider_type_display}"

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 120],
                tickvals=[50, 70, 90, 100, 110],
                ticktext=["50%", "70%", "90%", "100%", "110%"],
            )
        ),
        title=title_text,
        template='plotly_white',
        height=500,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5
        ),
    )

    # Add annotations for strengths/weaknesses
    annotations_text = []
    for i, (dur, val) in enumerate(zip(durations, values)):
        if val >= 90:
            annotations_text.append(f"✓ Strong: {duration_labels[dur]}")
        elif val < 70:
            annotations_text.append(f"⚠ Weak: {duration_labels[dur]}")

    if annotations_text:
        fig.add_annotation(
            text="<br>".join(annotations_text[:4]),  # Max 4 annotations
            xref="paper", yref="paper",
            x=1.15, y=0.5,
            showarrow=False,
            font=dict(size=11, color="gray"),
            align="left",
            xanchor="left",
        )

    return fig
