"""
LangGraph Agent for Training Program Planning - Expert Periodization Coach
"""
from typing import TypedDict, Annotated, Sequence, Dict, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from config import settings
from src.rag.knowledge_base import KnowledgeBase
from src.agent.adaptation import AdaptationEngine
import operator
import json
from datetime import datetime, timedelta
import re


# Agent State
class PlanState(TypedDict):
    """State of the training program planning agent"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_input: str
    user_profile: dict  # FTP, CTL, ATL, TSB, weight
    training_history: list  # Last 90 days of activities
    user_feedback_history: list  # Feedback from past workouts
    goal: dict  # Parsed goal: target_ftp, target_date, hours_per_week, sessions_per_week
    rag_context: str  # Periodization theory from RAG
    macro_plan: dict  # The full macro plan JSON
    week_detail: dict  # Detail for current week being planned
    reasoning: str
    program_rationale: str  # Full scientific rationale for the program structure


class PlanAgent:
    """LangGraph agent for creating and adapting multi-week training programs - Expert Coach"""

    # Periodization knowledge for RAG queries, organized by training concept
    PERIODIZATION_QUERIES = {
        "phase_structure": [
            "Traditional periodization Base Build Peak Taper cycling structure phases mesocycle macrocycle",
            "Block periodization cycling concentrated loading specific adaptations vs traditional linear",
            "Reverse periodization intensity first base later cycling winter training approach",
        ],
        "progressive_overload": [
            "Progressive overload training stress score TSS weekly ramp rate CTL chronic training load cycling",
            "Training load management acute chronic workload ratio injury prevention performance optimization",
        ],
        "recovery": [
            "Recovery adaptation supercompensation training stress cycling rest days deload week",
            "Overtraining syndrome prevention signs symptoms recovery cycling parasympathetic nervous system",
        ],
        "ftp_development": [
            "FTP improvement functional threshold power training sweet spot threshold intervals cycling",
            "Lactate threshold training progression cycling power duration curve improvement strategies",
        ],
        "race_preparation": [
            "Race preparation taper peaking supercompensation cycling event competition readiness",
            "Pre-competition training volume intensity manipulation cycling performance peak timing",
        ],
        "base_building": [
            "Aerobic base building zone 2 mitochondrial density capillary development cycling endurance foundation",
            "Polarized training model high volume low intensity cycling 80/20 approach threshold sessions",
        ],
        "intensity_distribution": [
            "Training intensity distribution polarized pyramidal threshold cycling performance models",
            "Zone distribution time in zone cycling training load monitoring weekly structure",
        ],
        "physiological_adaptation": [
            "Physiological adaptations cycling training VO2max cardiac output muscle fiber type",
            "Neuromuscular power development cycling sprint force cadence pedaling efficiency",
        ],
    }

    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.7,
            api_key=settings.openai_api_key,
        )
        self.kb = KnowledgeBase()
        self.adaptation_engine = AdaptationEngine()

        # Build the graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow for program planning"""
        workflow = StateGraph(PlanState)

        # Add nodes
        workflow.add_node("parse_goal", self.parse_goal)
        workflow.add_node("analyze_current_fitness", self.analyze_current_fitness)
        workflow.add_node("retrieve_periodization_theory", self.retrieve_periodization_theory)
        workflow.add_node("design_macro_plan", self.design_macro_plan)
        workflow.add_node("plan_current_week", self.plan_current_week)
        workflow.add_node("distribute_workouts", self.distribute_workouts)

        # Define edges (linear flow)
        workflow.set_entry_point("parse_goal")
        workflow.add_edge("parse_goal", "analyze_current_fitness")
        workflow.add_edge("analyze_current_fitness", "retrieve_periodization_theory")
        workflow.add_edge("retrieve_periodization_theory", "design_macro_plan")
        workflow.add_edge("design_macro_plan", "plan_current_week")
        workflow.add_edge("plan_current_week", "distribute_workouts")
        workflow.add_edge("distribute_workouts", END)

        return workflow.compile()

    def parse_goal(self, state: PlanState) -> PlanState:
        """Parse and validate the user's training goal"""
        user_input = state["user_input"]
        profile = state["user_profile"]

        prompt = f"""You are an expert cycling coach analyzing a rider's training goal.

RIDER PROFILE:
- Current FTP: {profile.get('ftp', 0)}W
- Weight: {profile.get('weight', 'unknown')}kg
- Current CTL: {profile.get('ctl', 0)}
- Current TSB: {profile.get('tsb', 0)}

USER GOAL:
{user_input}

Parse this goal and extract the following as valid JSON:
{{
    "goal_type": "ftp_target" or "race_prep" or "base_building",
    "target_ftp": <number or null>,
    "target_date": "YYYY-MM-DD",
    "hours_per_week": <number>,
    "sessions_per_week": <number>,
    "goal_description": "<concise 1-2 sentence summary>",
    "is_realistic": <true/false>,
    "validation_notes": "<explain why realistic or not, what adjustments if needed>"
}}

Validation rules:
- Typical FTP gain: 5-8W/month with good training. 10W/month is aggressive but possible.
- Under 5h/week = maintenance only. 8-12h = solid improvement. 15h+ = serious training.
- Minimum 4 weeks for any meaningful program. 8-16 weeks is the sweet spot.

Output ONLY valid JSON, no markdown."""

        messages = [SystemMessage(content=prompt)]
        response = self.llm.invoke(messages)

        try:
            content = response.content.strip()
            if "```" in content:
                content = content.split("```json")[-1].split("```")[0].strip() if "```json" in content else content.split("```")[1].split("```")[0].strip()
            goal_data = json.loads(content)
        except json.JSONDecodeError:
            goal_data = {
                "goal_type": "base_building",
                "target_ftp": None,
                "target_date": (datetime.now() + timedelta(weeks=12)).strftime("%Y-%m-%d"),
                "hours_per_week": 8,
                "sessions_per_week": 4,
                "goal_description": user_input,
                "is_realistic": True,
                "validation_notes": "Using default 12-week base building plan",
            }

        state["goal"] = goal_data
        state["reasoning"] = f"Goal parsed: {goal_data['goal_description']}\n{goal_data.get('validation_notes', '')}"

        return state

    def analyze_current_fitness(self, state: PlanState) -> PlanState:
        """Analyze rider's current fitness state and training history"""
        profile = state["user_profile"]
        history = state["training_history"]

        # Calculate training load trends
        recent_tss = [act.get("tss", 0) for act in history[-30:] if act.get("tss")]
        avg_weekly_tss = sum(recent_tss) / 4.3 if recent_tss else 0

        # Zone distribution analysis
        total_time_zones = {}
        for act in history:
            for i in range(1, 8):
                zone_key = f"time_zone{i}"
                total_time_zones[i] = total_time_zones.get(i, 0) + act.get(zone_key, 0)

        total_time = sum(total_time_zones.values())
        zone_pct = {z: (t / total_time * 100) if total_time > 0 else 0 for z, t in total_time_zones.items()}

        # Identify strengths/weaknesses
        strengths = []
        weaknesses = []

        z2_pct = zone_pct.get(2, 0)
        z45_pct = zone_pct.get(4, 0) + zone_pct.get(5, 0)
        z3_pct = zone_pct.get(3, 0)

        if z2_pct > 55:
            strengths.append("Strong aerobic base (>55% Z2)")
        elif z2_pct < 35:
            weaknesses.append("Insufficient aerobic base (<35% Z2)")

        if z45_pct > 15:
            strengths.append("Good high-intensity tolerance (Z4+Z5 >15%)")
        else:
            weaknesses.append("Limited threshold/VO2max work")

        if z3_pct > 30:
            weaknesses.append("Too much time in Z3 'grey zone' - inefficient training distribution")

        ctl = profile.get("ctl", 0)
        if ctl > 80:
            strengths.append(f"High fitness level (CTL={ctl:.0f})")
        elif ctl < 40:
            weaknesses.append(f"Low fitness base (CTL={ctl:.0f}), needs gradual build")

        fitness_analysis = f"""CURRENT FITNESS ANALYSIS:
- FTP: {profile.get('ftp', 0)}W | Weight: {profile.get('weight', '?')}kg
- CTL: {ctl:.0f} (Fitness) | ATL: {profile.get('atl', 0):.0f} (Fatigue) | TSB: {profile.get('tsb', 0):.1f} (Form)
- Average Weekly TSS (last 30 days): {avg_weekly_tss:.0f}
- Activities in history: {len(history)}

ZONE DISTRIBUTION (last 90 days):
- Z1 (Recovery): {zone_pct.get(1, 0):.1f}%
- Z2 (Endurance): {zone_pct.get(2, 0):.1f}%
- Z3 (Tempo): {zone_pct.get(3, 0):.1f}%
- Z4 (Threshold): {zone_pct.get(4, 0):.1f}%
- Z5 (VO2max): {zone_pct.get(5, 0):.1f}%
- Z6 (Anaerobic): {zone_pct.get(6, 0):.1f}%

STRENGTHS: {', '.join(strengths) if strengths else 'None identified (insufficient data)'}
WEAKNESSES: {', '.join(weaknesses) if weaknesses else 'None identified'}

READINESS: {'Fresh and ready (TSB>0)' if profile.get('tsb', 0) > 0 else 'Fatigued (TSB<0), start cautiously'}
"""

        state["reasoning"] += "\n\n" + fitness_analysis
        return state

    def retrieve_periodization_theory(self, state: PlanState) -> PlanState:
        """Retrieve relevant periodization theory from RAG - DEEP multi-query"""
        goal = state["goal"]
        goal_type = goal.get("goal_type", "base_building")

        # Select relevant query categories based on goal
        query_categories = ["phase_structure", "progressive_overload", "recovery", "intensity_distribution"]

        if goal_type == "ftp_target":
            query_categories.extend(["ftp_development", "physiological_adaptation"])
        elif goal_type == "race_prep":
            query_categories.extend(["race_preparation", "physiological_adaptation"])
        else:
            query_categories.extend(["base_building", "physiological_adaptation"])

        # Collect all queries
        all_queries = []
        for cat in query_categories:
            queries_for_cat = self.PERIODIZATION_QUERIES.get(cat, [])
            all_queries.extend(queries_for_cat)

        # Execute queries and deduplicate
        all_results = []
        seen_texts = set()

        for query in all_queries:
            try:
                results = self.kb.query(query, limit=3, score_threshold=0.4)
                for r in results:
                    text_key = r["text"][:100]
                    if text_key not in seen_texts:
                        seen_texts.add(text_key)
                        all_results.append(r)
            except Exception as e:
                print(f"RAG query failed: {e}")
                continue

        # Sort by score and take top 10 results, 1000 chars each (~10k chars total context)
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        rag_context = "\n\n---\n\n".join([
            f"[Source: {r['metadata'].get('source', 'unknown')}] (relevance: {r.get('score', 0):.2f})\n{r['text'][:1000]}"
            for r in all_results[:10]
        ])

        state["rag_context"] = rag_context if rag_context else "No RAG context available - use expert coaching principles."
        state["reasoning"] += f"\n\nRAG: Retrieved {len(all_results[:10])} theory passages from {len(all_queries)} queries"
        return state

    def design_macro_plan(self, state: PlanState) -> PlanState:
        """
        Design the macro-level periodization plan.
        This is a 2-step process:
        1. Expert reasoning about the optimal program structure (LLM call 1)
        2. Generate the structured JSON plan based on that reasoning (LLM call 2)
        """
        goal = state["goal"]
        profile = state["user_profile"]
        rag_context = state["rag_context"]
        fitness_analysis = state["reasoning"]

        # Calculate key parameters
        start_date = datetime.now()
        target_date = datetime.strptime(goal["target_date"], "%Y-%m-%d")
        total_weeks = max(4, min(24, (target_date - start_date).days // 7))

        current_ftp = profile.get("ftp", 250)
        target_ftp = goal.get("target_ftp") or (current_ftp + 20)
        hours_per_week = goal["hours_per_week"]
        sessions_per_week = goal["sessions_per_week"]
        current_ctl = profile.get("ctl", 50)
        avg_weekly_tss = current_ctl * 7  # Rough starting point

        # ========================
        # STEP 1: Expert reasoning about program design
        # ========================
        reasoning_prompt = f"""You are a world-class cycling coach and exercise physiologist designing a training program.

== SCIENTIFIC LITERATURE (from peer-reviewed research and coaching textbooks) ==
{rag_context}

== RIDER ANALYSIS ==
{fitness_analysis}

== PROGRAM PARAMETERS ==
- Goal: {goal['goal_description']}
- Current FTP: {current_ftp}W → Target: {target_ftp}W ({target_ftp - current_ftp}W gain needed)
- Timeline: {total_weeks} weeks (start: {start_date.strftime('%Y-%m-%d')}, target: {goal['target_date']})
- Available volume: {hours_per_week}h/week, {sessions_per_week} sessions/week
- Current CTL: {current_ctl}, recent weekly TSS: ~{avg_weekly_tss:.0f}

== YOUR TASK ==
Think deeply about the optimal program structure. Consider:

1. **Which periodization model suits this rider and goal?**
   - Traditional linear (gradual base→build→peak)?
   - Block periodization (concentrated loading blocks)?
   - Polarized (80% easy / 20% hard)?
   - Pyramidal (more moderate intensity than polarized)?
   Explain WHY based on the research above and the rider's profile.

2. **Phase design - be specific about EACH phase:**
   - What is the physiological PURPOSE of each phase?
   - What specific adaptations are we targeting? (e.g., mitochondrial biogenesis, lactate clearance, VO2max, neuromuscular)
   - What zone distribution within each phase? (not just "do Z2")
   - What types of key workouts define each phase?
   - How long should each phase be and WHY?

3. **Progression logic:**
   - How should TSS ramp within and between phases?
   - When should recovery weeks fall and why?
   - How does intensity distribution shift across phases?
   - What are the key transition points between phases?

4. **Risk assessment:**
   - Given the rider's current CTL and weaknesses, what risks exist?
   - Where might the plan need flexibility?
   - What signs should trigger plan modification?

5. **Weekly structure philosophy:**
   - How should hard/easy days be distributed?
   - What's the ideal session mix for each phase?
   - How to balance volume and intensity?

Write a DETAILED coaching rationale (500-800 words). Reference the SCIENTIFIC LITERATURE above.
This rationale will be shown to the rider to explain WHY the program is structured this way."""

        messages = [SystemMessage(content=reasoning_prompt)]
        reasoning_response = self.llm.invoke(messages)
        program_rationale = reasoning_response.content.strip()

        state["program_rationale"] = program_rationale
        state["reasoning"] += f"\n\n== PROGRAM DESIGN RATIONALE ==\n{program_rationale}"

        # ========================
        # STEP 2: Generate structured JSON plan based on reasoning
        # ========================
        json_prompt = f"""Based on your expert analysis below, generate a structured training plan as JSON.

== YOUR ANALYSIS ==
{program_rationale}

== CONSTRAINTS ==
- Total weeks: {total_weeks}
- Starting weekly TSS: ~{avg_weekly_tss:.0f} (based on current CTL {current_ctl})
- Max sustainable weekly TSS: ~{int(hours_per_week * 55)} (based on {hours_per_week}h/week)
- Sessions per week: {sessions_per_week}
- Recovery weeks: reduce TSS by 30-50% from previous loading week
- Max TSS increase between loading weeks: 10% per week
- All week numbers must be within 1 to {total_weeks}

Generate ONLY valid JSON in this exact format:
{{
    "total_weeks": {total_weeks},
    "periodization_model": "<name of model chosen>",
    "phases": [
        {{
            "name": "<phase name>",
            "weeks": [<start_week>, <end_week>],
            "purpose": "<1-2 sentence physiological purpose>",
            "weekly_tss_range": [<min_tss>, <max_tss>],
            "zone_focus": ["<primary zone type>", "<secondary>", ...],
            "zone_distribution": {{"Z1": 0.05, "Z2": 0.60, "Z3": 0.15, "Z4": 0.15, "Z5": 0.05}},
            "key_workouts": ["<workout description 1>", "<workout description 2>"],
            "intensity_profile": "<description>"
        }}
    ],
    "progression_rules": {{
        "max_tss_increase_pct": 10,
        "recovery_week_frequency": <3 or 4>,
        "recovery_week_tss_reduction_pct": <30-50>,
        "max_ctl_ramp_rate": 7
    }},
    "week_targets": [
        {{"week": 1, "tss": <number>, "phase": "<phase name>", "is_recovery": false, "focus_note": "<brief note>"}},
        ... for ALL {total_weeks} weeks
    ]
}}

RULES:
- week_targets MUST have EXACTLY {total_weeks} entries, one per week
- TSS progression must be smooth (no sudden jumps >10% between loading weeks)
- Recovery weeks should have TSS 30-50% lower than the previous loading week
- Phases must cover ALL weeks (no gaps)
- Output ONLY valid JSON, no markdown, no explanation"""

        messages = [SystemMessage(content=json_prompt)]
        json_response = self.llm.invoke(messages)

        # Parse JSON
        try:
            content = json_response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            macro_plan = json.loads(content)

            # Validate structure
            if "phases" not in macro_plan or "week_targets" not in macro_plan:
                raise ValueError("Missing required fields: phases or week_targets")

            if len(macro_plan["week_targets"]) < total_weeks * 0.8:
                raise ValueError(f"Insufficient week targets: got {len(macro_plan['week_targets'])}, expected ~{total_weeks}")

            # Store the rationale in macro_plan for persistence
            macro_plan["program_rationale"] = program_rationale

        except (json.JSONDecodeError, ValueError) as e:
            print(f"Macro plan parsing failed: {e}, using intelligent fallback")
            macro_plan = self._generate_fallback_plan(
                total_weeks=total_weeks,
                current_ctl=current_ctl,
                hours_per_week=hours_per_week,
                sessions_per_week=sessions_per_week,
                goal_type=goal.get("goal_type", "base_building"),
            )
            macro_plan["program_rationale"] = program_rationale

        state["macro_plan"] = macro_plan
        state["reasoning"] += f"\n\nMacro plan: {total_weeks} weeks, {len(macro_plan['phases'])} phases, model: {macro_plan.get('periodization_model', 'traditional')}"

        return state

    def _generate_fallback_plan(
        self, total_weeks: int, current_ctl: float, hours_per_week: float,
        sessions_per_week: int, goal_type: str
    ) -> dict:
        """Generate a scientifically-grounded fallback plan when LLM JSON parsing fails."""

        starting_tss = max(200, int(current_ctl * 7))
        peak_tss = int(hours_per_week * 55)

        # Phase proportions depend on goal and timeline
        if goal_type == "race_prep":
            # More build/peak, less base
            base_pct, build_pct, peak_pct, taper_pct = 0.35, 0.35, 0.15, 0.15
        elif goal_type == "ftp_target":
            # Balanced build
            base_pct, build_pct, peak_pct, taper_pct = 0.40, 0.35, 0.15, 0.10
        else:
            # Base building: more base
            base_pct, build_pct, peak_pct, taper_pct = 0.50, 0.25, 0.15, 0.10

        base_weeks = max(2, int(total_weeks * base_pct))
        build_weeks = max(2, int(total_weeks * build_pct))
        peak_weeks = max(1, int(total_weeks * peak_pct))
        taper_weeks = max(1, total_weeks - base_weeks - build_weeks - peak_weeks)

        phases = [
            {
                "name": "Base",
                "weeks": [1, base_weeks],
                "purpose": "Build aerobic foundation: mitochondrial density, capillary development, fat oxidation",
                "weekly_tss_range": [starting_tss, int(starting_tss * 1.3)],
                "zone_focus": ["Endurance", "Tempo", "Sweet Spot"],
                "zone_distribution": {"Z1": 0.05, "Z2": 0.60, "Z3": 0.20, "Z4": 0.10, "Z5": 0.05},
                "key_workouts": ["Long Z2 rides 2-3h", "Tempo blocks 3x15min", "Sweet Spot 2x20min"],
                "intensity_profile": "polarized_base: 80% Z1-Z2, 20% Z3-Z4",
            },
            {
                "name": "Build",
                "weeks": [base_weeks + 1, base_weeks + build_weeks],
                "purpose": "Develop race-specific power: lactate threshold, VO2max stimulus, muscular endurance",
                "weekly_tss_range": [int(starting_tss * 1.3), peak_tss],
                "zone_focus": ["Sweet Spot", "Threshold", "VO2max"],
                "zone_distribution": {"Z1": 0.05, "Z2": 0.45, "Z3": 0.10, "Z4": 0.20, "Z5": 0.15, "Z6": 0.05},
                "key_workouts": ["Threshold 2x20min @FTP", "VO2max 5x4min @120%", "Over-unders 4x8min"],
                "intensity_profile": "pyramidal: increasing threshold and VO2max volume",
            },
            {
                "name": "Peak",
                "weeks": [base_weeks + build_weeks + 1, base_weeks + build_weeks + peak_weeks],
                "purpose": "Sharpen race fitness: neuromuscular power, race-pace specificity, top-end power",
                "weekly_tss_range": [int(peak_tss * 0.9), peak_tss],
                "zone_focus": ["VO2max", "Threshold", "Anaerobic"],
                "zone_distribution": {"Z1": 0.05, "Z2": 0.35, "Z3": 0.05, "Z4": 0.20, "Z5": 0.25, "Z6": 0.10},
                "key_workouts": ["VO2max 6x3min @125%", "Race-pace simulations", "Sprint + threshold combos"],
                "intensity_profile": "race_specific: high intensity, controlled volume",
            },
            {
                "name": "Taper",
                "weeks": [base_weeks + build_weeks + peak_weeks + 1, total_weeks],
                "purpose": "Supercompensation: reduce volume 40-60%, maintain intensity, arrive fresh and sharp",
                "weekly_tss_range": [int(peak_tss * 0.4), int(peak_tss * 0.6)],
                "zone_focus": ["Recovery", "Endurance", "Threshold"],
                "zone_distribution": {"Z1": 0.15, "Z2": 0.50, "Z3": 0.05, "Z4": 0.15, "Z5": 0.10, "Z6": 0.05},
                "key_workouts": ["Openers 3x3min @105%", "Short sharp efforts", "Easy spinning"],
                "intensity_profile": "taper: volume down 40-60%, keep 2 short intensity sessions",
            },
        ]

        # Generate week-by-week targets with proper periodization
        week_targets = []
        current_tss = starting_tss
        recovery_counter = 0

        for week in range(1, total_weeks + 1):
            # Find phase for this week
            phase_name = "Base"
            phase_info = phases[0]
            for phase in phases:
                if phase["weeks"][0] <= week <= phase["weeks"][1]:
                    phase_name = phase["name"]
                    phase_info = phase
                    break

            recovery_counter += 1

            # Recovery week logic: every 3rd or 4th week
            # Use 3-week pattern for Build/Peak (more intense), 4-week for Base
            recovery_freq = 3 if phase_name in ["Build", "Peak"] else 4
            is_recovery = (recovery_counter >= recovery_freq)

            if is_recovery:
                recovery_counter = 0
                week_tss = int(current_tss * 0.6)
                focus_note = "Recovery/adaptation week - reduce volume, maintain some intensity"
            else:
                # Progressive overload within phase
                phase_start_week = phase_info["weeks"][0]
                phase_end_week = phase_info["weeks"][1]
                phase_duration = phase_end_week - phase_start_week + 1
                phase_progress = (week - phase_start_week) / max(1, phase_duration - 1)

                tss_low = phase_info["weekly_tss_range"][0]
                tss_high = phase_info["weekly_tss_range"][1]
                target = tss_low + (tss_high - tss_low) * phase_progress

                # Don't increase more than 10% from last loading week
                max_increase = current_tss * 1.10
                week_tss = int(min(target, max_increase))
                current_tss = week_tss

                focus_note = f"{phase_name} loading - focus on {', '.join(phase_info['zone_focus'][:2])}"

            week_targets.append({
                "week": week,
                "tss": week_tss,
                "phase": phase_name,
                "is_recovery": is_recovery,
                "focus_note": focus_note,
            })

        return {
            "total_weeks": total_weeks,
            "periodization_model": "traditional_linear",
            "phases": phases,
            "progression_rules": {
                "max_tss_increase_pct": 10,
                "recovery_week_frequency": 4,
                "recovery_week_tss_reduction_pct": 40,
                "max_ctl_ramp_rate": 7,
            },
            "week_targets": week_targets,
        }

    def plan_current_week(self, state: PlanState) -> PlanState:
        """Plan the current week with adaptation based on recent performance"""
        macro_plan = state["macro_plan"]
        profile = state["user_profile"]
        goal = state["goal"]

        current_week_number = state.get("week_detail", {}).get("week_number", 1)

        # Find target for this week from macro plan
        week_target = next(
            (wt for wt in macro_plan["week_targets"] if wt["week"] == current_week_number),
            macro_plan["week_targets"][0],
        )

        target_tss = week_target["tss"]
        phase = week_target["phase"]
        is_recovery = week_target["is_recovery"]
        focus_note = week_target.get("focus_note", "")

        # Find phase details
        phase_info = next((p for p in macro_plan["phases"] if p["name"] == phase), macro_plan["phases"][0])
        zone_focus = phase_info["zone_focus"]

        # Apply fatigue-based adaptations
        adjusted_tss = target_tss
        adaptation_notes = ""

        tsb = profile.get("tsb", 0)
        if tsb < -20:
            adjusted_tss = target_tss * 0.5
            adaptation_notes = f"FORCED RECOVERY - TSB critically low ({tsb:.1f}). Reducing load by 50%."
        elif tsb < -15:
            adjusted_tss = target_tss * 0.8
            adaptation_notes = f"Reduced TSS by 20% due to high fatigue (TSB: {tsb:.1f})"
        elif tsb < -10:
            adjusted_tss = target_tss * 0.9
            adaptation_notes = f"Minor load reduction due to accumulated fatigue (TSB: {tsb:.1f})"

        # Build coaching instructions
        key_workouts = phase_info.get("key_workouts", [])
        phase_purpose = phase_info.get("purpose", "")

        week_instructions = f"""Week {current_week_number} - {phase} Phase {'(RECOVERY WEEK)' if is_recovery else ''}

Target TSS: {adjusted_tss:.0f} | Zone Focus: {', '.join(zone_focus)}
Phase Purpose: {phase_purpose}
{focus_note}

Key Workouts This Phase: {', '.join(key_workouts[:3]) if key_workouts else 'See zone focus'}

{'Adaptation: ' + adaptation_notes if adaptation_notes else ''}
"""

        state["week_detail"] = {
            "week_number": current_week_number,
            "phase": phase,
            "target_tss": adjusted_tss,
            "target_hours": goal["hours_per_week"],
            "target_sessions": goal["sessions_per_week"],
            "zone_focus": zone_focus,
            "week_instructions": week_instructions,
            "adaptation_notes": adaptation_notes,
            "is_recovery": is_recovery,
        }

        return state

    def distribute_workouts(self, state: PlanState) -> PlanState:
        """Distribute weekly TSS across N sessions with proper sequencing"""
        week_detail = state["week_detail"]
        profile = state["user_profile"]

        target_tss = week_detail["target_tss"]
        sessions_per_week = week_detail["target_sessions"]
        zone_focus = week_detail["zone_focus"]
        phase = week_detail.get("phase", "Base")

        # Use AdaptationEngine to distribute workouts
        workouts = self.adaptation_engine.adjust_week_distribution(
            target_tss=target_tss,
            sessions_per_week=sessions_per_week,
            zone_focus=zone_focus,
            current_profile=profile,
        )

        # Add detailed instructions for each workout
        for i, workout in enumerate(workouts):
            instructions = f"""{workout['workout_type']} session for {phase} phase (Week {week_detail['week_number']}).
Target TSS: {workout['target_tss']:.0f}, Duration: ~{workout['target_duration']}min
Phase focus: {', '.join(zone_focus[:2]) if zone_focus else 'General'}
Current rider state: FTP={profile.get('ftp', 0)}W, CTL={profile.get('ctl', 0):.0f}, TSB={profile.get('tsb', 0):.1f}
"""
            workout["instructions"] = instructions

        week_detail["planned_workouts"] = workouts
        state["week_detail"] = week_detail

        state["reasoning"] += f"\n\nWeek {week_detail['week_number']} distributed: {len(workouts)} sessions totaling {target_tss:.0f} TSS"

        return state

    def create_program(
        self, user_input: str, user_profile: dict, training_history: list, feedback_history: list
    ) -> dict:
        """
        Main entry point: Create a full training program.

        Returns:
            dict with macro_plan, first_week_detail, reasoning, goal
        """
        initial_state = PlanState(
            messages=[],
            user_input=user_input,
            user_profile=user_profile,
            training_history=training_history,
            user_feedback_history=feedback_history,
            goal={},
            rag_context="",
            macro_plan={},
            week_detail={},
            reasoning="",
            program_rationale="",
        )

        final_state = self.graph.invoke(initial_state)

        return {
            "macro_plan": final_state["macro_plan"],
            "first_week_detail": final_state["week_detail"],
            "reasoning": final_state["reasoning"],
            "goal": final_state["goal"],
            "program_rationale": final_state.get("program_rationale", ""),
        }

    def plan_week(
        self,
        program,  # TrainingProgram model instance
        week_number: int,
        user_profile: dict,
        recent_weeks: list,  # List of WeekPlan instances
    ) -> dict:
        """
        Re-plan a specific week with adaptation.
        """
        # Load macro plan from program
        macro_plan = json.loads(program.macro_plan_json)

        # Check if adaptations are needed
        adjustments = self.adaptation_engine.calculate_adjustments(
            program=program,
            current_week_number=week_number,
            current_profile=user_profile,
            recent_weeks=recent_weeks,
        )

        # Build simplified state for nodes 5-6 only
        state = PlanState(
            messages=[],
            user_input="",
            user_profile=user_profile,
            training_history=[],
            user_feedback_history=[],
            goal={
                "hours_per_week": program.hours_per_week,
                "sessions_per_week": program.sessions_per_week,
            },
            rag_context="",
            macro_plan=macro_plan,
            week_detail={"week_number": week_number},
            reasoning="",
            program_rationale="",
        )

        # Run plan_current_week node
        state = self.plan_current_week(state)

        # Apply adjustments from adaptation engine
        if adjustments["tss_multiplier"] != 1.0:
            state["week_detail"]["target_tss"] *= adjustments["tss_multiplier"]
            state["week_detail"]["adaptation_notes"] = "\n".join(adjustments["reasons"])

        # Run distribute_workouts node
        state = self.distribute_workouts(state)

        return {
            "week_detail": state["week_detail"],
            "reasoning": state["reasoning"],
        }
