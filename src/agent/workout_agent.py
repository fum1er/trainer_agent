"""
LangGraph Agent for Workout Generation - Expert Cycling Coach
"""
from typing import TypedDict, Annotated, Sequence, Literal, Optional
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from config import settings
from src.rag.knowledge_base import KnowledgeBase
from src.utils.training_zones_calculator import (
    calculate_cp_zones,
    get_workout_type_zones,
    format_zones_for_prompt,
)
from src.database.database import get_db
from src.database.models import ZwiftWorkout
import operator
import random
import re


class WorkoutPlanOutput(BaseModel):
    """Structured output for workout plan generation"""
    NAME: str = Field(description="Creative workout name, e.g. 'Pyramid VO2max Crusher' or 'SFR Force Builder'")
    TYPE: str = Field(description="Workout type: Endurance, Tempo, Sweet Spot, Threshold, VO2max, Anaerobic, Force, or Recovery")
    DURATION: int = Field(description="Total workout duration in minutes (number only)")
    TSS: float = Field(description="Estimated Training Stress Score (number only)")
    IF: float = Field(description="Estimated Intensity Factor as decimal, e.g. 0.88 (number only)")
    STRUCTURE: str = Field(description="Detailed interval structure with specific power percentages, durations, cadence targets")
    RATIONALE: str = Field(description="2-4 sentences citing specific passage numbers and scientific concepts from the training theory")
    CADENCE_NOTES: str = Field(default="", description="Specific cadence targets if relevant, e.g. 'low cadence 55rpm for SFR blocks'")


def safe_parse_number(value, default=0.0):
    """Extract a number from a string that may contain extra text like '52 (estimated)'."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r'[\d.]+', str(value))
    return float(match.group()) if match else default


# Agent State
class AgentState(TypedDict):
    """State of the workout generation agent"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_input: str
    user_profile: dict  # FTP, CTL, ATL, TSB, target_workout_type
    training_history: list  # Recent activities
    user_feedback_history: list  # Past workout feedbacks for memory
    rag_context: str
    memory_context: str
    workout_structure: dict
    workout_xml: str
    reasoning: str
    target_workout_type: str  # Inferred workout type for context-aware processing


class WorkoutAgent:
    """LangGraph agent for generating personalized cycling workouts - Expert Coach"""

    # Expert coaching knowledge organized by physiological objective
    COACHING_KNOWLEDGE = {
        "Endurance": {
            "styles": [
                "Steady Z2: 60-75% FTP continu, cadence 80-90rpm",
                "Progressive endurance: start 60%, +2% tous les 15min jusqu'a 72%",
                "Tempo touches: Z2 base + 3x5min a 80% FTP integres",
                "Cadence play: Z2 avec alternance 5min low cadence (60rpm) / 5min high (100rpm)",
                "Fartlek endurance: Z2 base + accelerations spontanees de 30s-2min a 80-85%",
            ],
            "theory_queries": [
                "Aerobic base building zone 2 endurance mitochondrial density cycling",
                "Long slow distance training adaptations fat oxidation cycling",
            ],
        },
        "Sweet Spot": {
            "styles": [
                "Classic blocks: 3x12min a 88-93%, 4min recovery",
                "Long block: 2x20min a 88-90%, 5min recovery",
                "Progressive SS: 10min@88% + 12min@90% + 15min@92%, 4min recup entre",
                "Over-under SS: 4x(3min@95% + 3min@85%), 3min recup entre sets",
                "Criss-cross: 3x15min alternant 1min@92% / 1min@85%, 4min recup",
                "SS + sprints: 2x15min@90% avec 3x10s sprints@150% integres chaque 5min",
                "Tempo to SS ramp: 20min@80% -> 15min@88% -> 10min@93%, progression dans la seance",
            ],
            "theory_queries": [
                "Sweet spot training 88-94% FTP effectiveness time efficiency cycling",
                "Sub-threshold intervals muscular endurance adaptations cycling training",
            ],
        },
        "Threshold": {
            "styles": [
                "Classic: 2x20min a 95-100%, 5min recup",
                "Ascending: 10min@95% + 15min@98% + 10min@100%",
                "Short-sharp: 6x8min a 100-105%, 4min recup",
                "Over-under threshold: 3x(4min@105% + 4min@90%), 5min recup entre sets",
                "Ramp to threshold: 3x12min rampe de 90% a 105%, 5min recup",
                "Cruise intervals: 4x10min@100% avec seulement 2min recup (specifique TT)",
                "Threshold + sprints: 2x15min@98% avec 2x8s sprints max integres",
                "Step-up: 5min@90% + 5min@95% + 5min@100% + 5min@105%, 5min recup, x2",
            ],
            "theory_queries": [
                "Functional threshold power FTP intervals lactate threshold training cycling",
                "Threshold training time trial power duration relationship cycling",
            ],
        },
        "VO2max": {
            "styles": [
                "Classic: 5x5min a 110-115%, 5min recup",
                "Short: 8x3min a 115-120%, 3min recup",
                "Pyramid: 2-3-4-5-4-3-2min a 115%, recup egale a l'effort",
                "Billats 30/30: 2 sets de 10x(30s@120% + 30s@55%), 5min entre sets",
                "Micro-bursts 40/20: 3 sets de 10x(40s@130% + 20s@55%), 5min entre sets",
                "Descending rest: 5x4min@112%, rest = 4min, 3.5, 3, 2.5, 2min",
                "Tabata-style: 8x(20s@170% + 10s rest), x3 sets, 4min entre sets",
                "VO2max ramp: 4x(2min@105% + 2min@110% + 2min@115%), 5min recup",
                "Ronnestad 30/15: 3 sets de 13x(30s@130% + 15s@55%), 3min entre sets",
            ],
            "theory_queries": [
                "VO2max intervals cycling high intensity training maximal aerobic power",
                "Short high intensity intervals HIIT cycling VO2 kinetics oxygen uptake",
            ],
        },
        "Anaerobic": {
            "styles": [
                "Sprint repeats: 10x(15s all-out + 45s recup), x3 sets, 5min entre sets",
                "Sprint-endurance: 6x(30s@150% + 4.5min@55%)",
                "Standing starts: 8x(10s sprint depart arrete + 2min recup)",
                "Neuromuscular power: 12x(8s sprint max + 52s recup facile)",
                "Sprint + threshold combo: 4x(10s sprint max + 4min@95% FTP + 3min recup)",
                "Over-geared sprints: 6x(20s cadence 50rpm puissance max + 3min recup)",
                "Micro-bursts anaerobiques: 10x(15s@200% + 45s@55%), x2 sets",
                "Sprint ladders: 10s, 15s, 20s, 30s, 20s, 15s, 10s all-out, 2min recup entre chaque",
            ],
            "theory_queries": [
                "Anaerobic capacity sprint training cycling neuromuscular power",
                "Sprint interval training SIT cycling performance peak power",
            ],
        },
        "Force": {
            "styles": [
                "SFR classique: 6x5min a 80-90% FTP cadence 50-55rpm, 5min recup cadence libre",
                "SFR progressif: 5min@76%/50rpm + 5min@82%/55rpm + 5min@88%/55rpm + 5min@92%/50rpm",
                "Single-leg focus: 4x(3min jambe gauche + 3min jambe droite) a 75% FTP cadence 50rpm, 2min recup",
                "Torque intervals: 8x3min a 85-90% FTP cadence 50rpm en danseuse, 3min recup",
                "Muscular endurance: 2x20min a 82-88% FTP cadence 55-60rpm (big gear), 5min recup",
                "Force ladder: 3min@76% + 4min@82% + 5min@88% + 4min@82% + 3min@76%, all at 50-55rpm, 3min recup entre",
            ],
            "theory_queries": [
                "Muscular endurance big gear aerobic force cycling training CP30 CP60 power zones",
                "Low cadence high torque muscular tension cycling training adaptations",
            ],
        },
        "Recovery": {
            "styles": [
                "Easy spin: 45-60min a 50-55%, cadence 85-95rpm",
                "Active recovery + openers: 50min@50% + 3x1min a 70% pour activer les jambes",
                "Super easy: 45min jamais au-dessus de 55%, focus pedalage souple",
                "Recovery + stretches: 30min@50% + 15min cadence variee (70-100rpm) tres facile",
            ],
            "theory_queries": [
                "Active recovery rides cycling regeneration fatigue management blood flow",
                "Recovery training load management detraining prevention cycling",
            ],
        },
        "Tempo": {
            "styles": [
                "Steady tempo: 40-60min continu a 76-87% FTP",
                "Tempo blocks: 3x15min a 80-87%, 5min recup",
                "Ascending tempo: 15min@76% + 15min@82% + 15min@87%",
                "Tempo + sprints: 30min@82% avec 5x10s sprints integres toutes les 6min",
                "Sweet spot touch: 20min@82% + 10min@90% + 20min@82%",
                "Tempo fartlek: 45min entre 76-90% avec variations libres toutes les 3-5min",
            ],
            "theory_queries": [
                "Tempo training zone 3 cycling muscular endurance sustained power",
                "Moderate intensity training cycling lactate clearance aerobic capacity",
            ],
        },
    }

    WARMUP_STYLES = {
        "Recovery": "Warmup (10 min, gentle ramp from 0.45 to 0.55, cadence 85-95rpm)",
        "Endurance": "Warmup (10-15 min, gradual ramp from 0.50 to 0.65, cadence 80-90rpm)",
        "Tempo": "Warmup (10-15 min, ramp from 0.50 to 0.70, cadence 85rpm)",
        "Sweet Spot": "Warmup (10-15 min, ramp from 0.50 to 0.70, then 2x30s openers at 0.90 with 30s rest)",
        "Threshold": "Warmup (15 min, ramp from 0.50 to 0.75, including 3x1min builds to 0.95 with 1min rest)",
        "VO2max": "Warmup (15 min, ramp from 0.50 to 0.75, then 3x30s at 1.10 with 30s rest to prime legs)",
        "Anaerobic": "Warmup (15 min, ramp from 0.50 to 0.70, then 3x8s progressive sprints with 1min rest)",
        "Force": "Warmup (15 min, ramp from 0.50 to 0.70, then 2x1min at 0.70 low cadence 60rpm)",
    }

    def __init__(self):
        self.kb = KnowledgeBase()
        self.llm = ChatOpenAI(
            model="gpt-4o",
            api_key=settings.openai_api_key,
            temperature=0.7,
        )

        # Build graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("analyze_rider", self.analyze_rider)
        workflow.add_node("retrieve_memory", self.retrieve_memory)
        workflow.add_node("retrieve_theory", self.retrieve_theory)
        workflow.add_node("plan_workout", self.plan_workout)
        workflow.add_node("generate_structure", self.generate_structure)
        workflow.add_node("format_zwo", self.format_zwo)

        # Define edges
        workflow.set_entry_point("analyze_rider")
        workflow.add_edge("analyze_rider", "retrieve_memory")
        workflow.add_edge("retrieve_memory", "retrieve_theory")
        workflow.add_edge("retrieve_theory", "plan_workout")
        workflow.add_edge("plan_workout", "generate_structure")
        workflow.add_edge("generate_structure", "format_zwo")
        workflow.add_edge("format_zwo", END)

        return workflow.compile()

    def analyze_rider(self, state: AgentState) -> AgentState:
        """Analyze rider's current fitness and fatigue"""
        profile = state["user_profile"]
        history = state["training_history"]

        analysis_prompt = f"""
Analyze this cyclist's current state:

Profile:
- FTP: {profile.get('ftp')} watts
- CTL (Fitness): {profile.get('ctl')}
- ATL (Fatigue): {profile.get('atl')}
- TSB (Form): {profile.get('tsb')}

Recent Training (last 7 days):
{self._format_recent_activities(history)}

TSB Guidelines:
- TSB > 5: Fresh and rested - can handle high intensity (Threshold, VO2max, Sweet Spot)
- TSB 0 to 5: Good balance - moderate to hard workouts (Sweet Spot, Tempo, Threshold)
- TSB -10 to 0: Accumulating fatigue - keep intensity moderate (Tempo, Sweet Spot) or endurance
- TSB < -10: Fatigued - MUST prioritize recovery (Recovery rides at 50-60% FTP or complete rest)

Provide a 2-sentence analysis of their current state and what intensity is appropriate RIGHT NOW.
"""

        response = self.llm.invoke([HumanMessage(content=analysis_prompt)])

        # Detailed debug log
        state["reasoning"] = "=" * 60 + "\n"
        state["reasoning"] += "STEP 1: ANALYZE RIDER\n"
        state["reasoning"] += "=" * 60 + "\n\n"
        state["reasoning"] += f"INPUT - User Request: {state['user_input']}\n"
        state["reasoning"] += f"INPUT - Target Type: {state.get('target_workout_type', 'Auto')}\n\n"
        state["reasoning"] += f"INPUT - Profile:\n"
        state["reasoning"] += f"  FTP: {profile.get('ftp')}W\n"
        state["reasoning"] += f"  CTL: {profile.get('ctl')}, ATL: {profile.get('atl')}, TSB: {profile.get('tsb')}\n\n"
        state["reasoning"] += f"INPUT - Recent Activities ({len(history)} last 7 days):\n"
        state["reasoning"] += f"{self._format_recent_activities(history)}\n\n"
        state["reasoning"] += f"OUTPUT - LLM Analysis:\n{response.content}\n\n"
        state["messages"] = [SystemMessage(content=response.content)]

        return state

    def retrieve_memory(self, state: AgentState) -> AgentState:
        """Retrieve user's past workout feedbacks with type-aware analysis"""
        feedback_history = state.get("user_feedback_history", [])

        if not feedback_history:
            state["memory_context"] = ""
            state["reasoning"] += "No previous feedback found\n\n"
            return state

        target_type = state.get("target_workout_type", "Unknown")

        memory_prompt = f"""
Analyze this user's workout feedback history to extract preferences.
The user is about to generate a **{target_type}** workout.

CRITICAL RULES FOR FEEDBACK INTERPRETATION:
- Feedback marked "MOST RELEVANT" is from the SAME workout type ({target_type}).
  Use this feedback to adjust intensity, interval structure, and difficulty for this specific type.
- Feedback from OTHER workout types should ONLY inform general preferences (preferred duration, cadence, etc.)
- NEVER apply intensity feedback from one type to another type.
  Example: If Recovery feedback says "too hard", do NOT reduce VO2max intensity.
  That feedback means the recovery ride had too much power, not that the user can't handle hard work.

{self._format_feedback_history(feedback_history)}

Summarize in 2-3 bullet points:
- Specific preferences for {target_type} workouts (if available)
- General preferences that apply across all workout types (duration, cadence, interval style)
- Recommended adjustments for this upcoming {target_type} workout
"""

        response = self.llm.invoke([HumanMessage(content=memory_prompt)])

        state["memory_context"] = f"User Preferences (from past feedback):\n{response.content}\n\n"

        state["reasoning"] += "=" * 60 + "\n"
        state["reasoning"] += "STEP 2: RETRIEVE MEMORY (feedback history)\n"
        state["reasoning"] += "=" * 60 + "\n\n"
        same_type = [fb for fb in feedback_history if fb.get("is_same_type", False)]
        other_type = [fb for fb in feedback_history if not fb.get("is_same_type", False)]
        state["reasoning"] += f"INPUT - {len(feedback_history)} feedbacks found in DB:\n"
        state["reasoning"] += f"  Same type ({target_type}): {len(same_type)}\n"
        state["reasoning"] += f"  Other types: {len(other_type)}\n"
        for fb in feedback_history:
            marker = "[SAME TYPE]" if fb.get("is_same_type") else "[OTHER]"
            state["reasoning"] += f"  {marker} {fb.get('workout_name', '?')} ({fb.get('workout_type', '?')}) - "
            state["reasoning"] += f"difficulty={fb.get('difficulty', '?')}, rating={fb.get('rating', '?')}\n"
            if fb.get("notes"):
                state["reasoning"] += f"    notes: {fb['notes']}\n"
        state["reasoning"] += f"\nOUTPUT - LLM Summary:\n{response.content}\n\n"

        return state

    def _run_rag_pipeline(self, queries: list, score_threshold: float = 0.55, top_n: int = 8, metadata_filter: dict = None) -> list:
        """Run cross-referenced RAG queries with deduplication and score boosting.

        Args:
            queries: List of search queries
            score_threshold: Minimum similarity score
            top_n: Number of top results to return
            metadata_filter: Optional Qdrant metadata filter (e.g. {"type": "workout"})

        Returns:
            List of top results sorted by boosted score
        """
        all_results = []
        seen_texts = set()

        for query in queries:
            try:
                results = self.kb.query(query, limit=5, score_threshold=score_threshold, metadata_filter=metadata_filter)
                for r in results:
                    text_key = r["text"][:150]
                    if text_key not in seen_texts:
                        seen_texts.add(text_key)
                        r["query_matches"] = 1
                        r["boosted_score"] = r.get("score", 0)
                        all_results.append(r)
                    else:
                        for existing in all_results:
                            if existing["text"][:150] == text_key:
                                existing["query_matches"] += 1
                                existing["boosted_score"] = existing.get("score", 0) * (1 + 0.1 * existing["query_matches"])
                                break
            except Exception as e:
                print(f"Warning: RAG query failed: {e}")
                continue

        all_results.sort(key=lambda x: x.get("boosted_score", 0), reverse=True)
        return all_results[:top_n]

    def retrieve_theory(self, state: AgentState) -> AgentState:
        """Retrieve training theory with SEPARATE pipelines for books and workouts."""
        user_input = state["user_input"]
        profile = state["user_profile"]
        target_type = state.get("target_workout_type", "")
        tsb = profile.get("tsb", 0)

        # Build queries
        queries = self._build_rag_queries(user_input, target_type, tsb)

        # ==========================================
        # PIPELINE 1: BOOKS (training science theory)
        # Filter: exclude workouts, only books/PDFs
        # ==========================================
        book_queries = queries  # All queries apply to books
        book_results = self._run_rag_pipeline(
            book_queries, score_threshold=0.50, top_n=8,
            metadata_filter={"type": "book"}
        )

        # ==========================================
        # PIPELINE 2: ZWIFT WORKOUTS (proven structures)
        # Filter: only workouts
        # Queries focused on practical structures
        # ==========================================
        workout_queries = []
        if target_type:
            workout_queries.append(f"{target_type} cycling workout intervals structure")
            workout_queries.append(f"{target_type} {user_input}")
            # Add type-specific workout queries
            workout_enrichment = {
                "Sweet Spot": "sweet spot 88-94% FTP over-under progressive intervals",
                "VO2max": "VO2max high intensity short intervals 3-5 minutes 110-120% FTP",
                "Threshold": "threshold FTP 95-105% cruise intervals 2x20 time trial",
                "Endurance": "endurance zone 2 60-75% long steady aerobic",
                "Recovery": "recovery easy 50-55% FTP active recovery spin",
                "Tempo": "tempo zone 3 76-87% moderate sustained",
                "Anaerobic": "sprint anaerobic neuromuscular 150%+ short bursts tabata",
                "Force": "force SFR low cadence 50-60rpm strength torque big gear",
            }
            workout_queries.append(workout_enrichment.get(target_type, f"{target_type} workout"))
        else:
            workout_queries.append(f"cycling workout {user_input}")

        workout_results = self._run_rag_pipeline(
            workout_queries, score_threshold=0.50, top_n=5,
            metadata_filter={"type": "workout"}
        )

        # ==========================================
        # BUILD CONTEXT: books first, then workouts
        # ==========================================
        context = "== TRAINING SCIENCE (from cycling books) ==\n\n"
        for i, result in enumerate(book_results):
            source = result.get("metadata", {}).get("source", "Unknown")
            score = result.get("boosted_score", 0)
            matches = result.get("query_matches", 1)
            validation = " HIGH CONFIDENCE" if matches >= 3 else " Cross-validated" if matches >= 2 else ""
            context += f"Book {i+1}. [{source}] (score: {score:.2f}, {matches} queries){validation}\n"
            context += f"{result['text'][:1000]}\n\n"

        if not book_results:
            context += "No relevant theory found.\n\n"

        context += "\n== PROVEN WORKOUT STRUCTURES (from Zwift library - 1400+ workouts) ==\n\n"
        for i, result in enumerate(workout_results):
            score = result.get("boosted_score", 0)
            context += f"Zwift {i+1}. (similarity: {score:.2f})\n"
            context += f"{result['text'][:800]}\n\n"

        if not workout_results:
            context += "No similar workouts found.\n\n"

        state["rag_context"] = context

        # ==========================================
        # DEBUG REASONING
        # ==========================================
        state["reasoning"] += "=" * 60 + "\n"
        state["reasoning"] += "STEP 3: RETRIEVE THEORY (dual RAG pipeline)\n"
        state["reasoning"] += "=" * 60 + "\n\n"

        # Book pipeline debug
        state["reasoning"] += f"--- PIPELINE 1: BOOKS ({len(book_queries)} queries) ---\n"
        for qi, q in enumerate(book_queries, 1):
            state["reasoning"] += f"  Q{qi}: {q}\n"
        state["reasoning"] += f"\n  {len(book_results)} book passages retrieved:\n"
        for i, r in enumerate(book_results):
            source = r.get("metadata", {}).get("source", "?")
            score = r.get("boosted_score", 0)
            matches = r.get("query_matches", 1)
            state["reasoning"] += f"  [{i+1}] {source} (score={score:.2f}, queries={matches})\n"
            state["reasoning"] += f"      {r['text'][:120]}...\n"

        # Workout pipeline debug
        state["reasoning"] += f"\n--- PIPELINE 2: ZWIFT WORKOUTS ({len(workout_queries)} queries) ---\n"
        for qi, q in enumerate(workout_queries, 1):
            state["reasoning"] += f"  Q{qi}: {q}\n"
        state["reasoning"] += f"\n  {len(workout_results)} workout passages retrieved:\n"
        for i, r in enumerate(workout_results):
            score = r.get("boosted_score", 0)
            # Extract workout name
            name_match = re.search(r'# Zwift Workout:\s*(.+?)(?:\n|$)', r['text'])
            name = name_match.group(1).strip() if name_match else "?"
            state["reasoning"] += f"  [{i+1}] {name} (score={score:.2f})\n"
            state["reasoning"] += f"      {r['text'][:120]}...\n"
        state["reasoning"] += "\n"

        return state

    def _build_rag_queries(self, user_input: str, target_type: str, tsb: float) -> list:
        """Build adaptive RAG queries with cross-referenced context for deep understanding."""
        queries = []

        # Query 1: User's original request
        queries.append(f"Cycling training: {user_input}")

        # Query 2-4: Type-specific training theory (original queries)
        if target_type and target_type in self.COACHING_KNOWLEDGE:
            for tq in self.COACHING_KNOWLEDGE[target_type]["theory_queries"]:
                queries.append(tq)

        # Query 5-8: Deep cross-reference queries for workout prescription details
        if target_type:
            cross_ref = {
                "Force": [
                    "Muscular endurance workout CP30 CP60 CP90 power zones big gear cycling training prescription",
                    "tempo sweet spot intensity low cadence force training cycling workout intervals duration",
                    "aerobic endurance force combination sustained power workout examples cycling",
                    "big gear low cadence workout intervals repetitions rest muscular endurance training",
                ],
                "VO2max": [
                    "VO2max interval duration 3 4 5 minutes power intensity optimal training cycling",
                    "high intensity interval training HIIT 30/30 40/20 work rest ratio cycling",
                    "VO2max workout examples intervals sets repetitions cycling training prescription",
                    "maximal aerobic power intervals duration recovery cycling workout design",
                ],
                "Threshold": [
                    "lactate threshold FTP training 20 minutes intensity duration cycling time trial",
                    "threshold intervals 2x20 3x12 8x8 training load cycling workout prescription",
                    "FTP intervals workout examples duration rest ratio cycling training",
                    "sub-maximal sustained power threshold training cycling workout structure",
                ],
                "Sweet Spot": [
                    "sweet spot training 88-94 FTP 3x12 2x20 optimal duration cycling workout",
                    "sub-threshold training 85-95 percent intervals duration cycling prescription",
                    "sweet spot workout examples over-under intervals cycling training",
                    "tempo threshold sustained power intervals workout cycling training design",
                ],
                "Anaerobic": [
                    "sprint interval training 10 15 30 seconds power output cycling workout",
                    "anaerobic capacity training work rest ratio 30s 1min cycling prescription",
                    "neuromuscular power sprint workout examples cycling training intervals",
                    "maximal sprint training repetitions sets recovery cycling workout design",
                ],
                "Endurance": [
                    "zone 2 aerobic training 60 90 120 minutes duration cycling workout",
                    "base training endurance ride 2-4 hours intensity cycling prescription",
                    "aerobic endurance workout long steady distance cycling training",
                    "low intensity training volume duration cycling base building workout",
                ],
                "Tempo": [
                    "tempo training zone 3 76-90 FTP 20-60 minutes cycling workout prescription",
                    "moderate intensity training tempo intervals duration cycling workout examples",
                    "tempo ride 30-60 minutes sustained power cycling training design",
                    "sub-threshold tempo training workout structure cycling prescription",
                ],
                "Recovery": [
                    "active recovery training 30-60 minutes 50-60 percent FTP cycling workout",
                    "recovery ride intensity 55 percent optimal regeneration cycling prescription",
                    "easy spin recovery workout duration intensity cycling training",
                    "regeneration ride low intensity active recovery cycling workout design",
                ],
            }

            if target_type in cross_ref:
                queries.extend(cross_ref[target_type])

        # Query 7: Fitness-state-specific
        if tsb < -10:
            queries.append("Overreaching fatigue management recovery training load reduction cycling")
        elif tsb > 5:
            queries.append("Peak performance supercompensation high intensity periodization cycling")
        else:
            queries.append("Progressive overload training stress balance optimal loading cycling")

        return queries

    def retrieve_similar_workouts(self, target_type: str, duration_minutes: int, tss_target: int = None, limit: int = 5, theory_keywords: str = ""):
        """
        Semantic search in Qdrant vector DB for similar Zwift workouts.
        Uses embedding similarity (nearest neighbor) instead of rigid SQL filters.
        Can be enriched with theory keywords from training science literature.

        Args:
            target_type: Workout type (e.g., "Sweet Spot", "VO2max")
            duration_minutes: Target duration
            tss_target: Optional TSS target
            limit: Number of workouts to retrieve
            theory_keywords: Key concepts from training theory to enrich the search
        """
        # Build a rich semantic query
        query_parts = []
        if target_type:
            query_parts.append(f"{target_type} cycling workout")
        if duration_minutes:
            query_parts.append(f"{duration_minutes} minutes")
        if tss_target:
            query_parts.append(f"TSS {tss_target}")

        # Enrich with theory-driven keywords for smarter semantic matching
        if theory_keywords:
            query_parts.append(theory_keywords[:200])
        else:
            type_enrichment = {
                "Sweet Spot": "sweet spot 88-94% FTP intervals over-under progressive muscular endurance",
                "VO2max": "VO2max high intensity 110-120% FTP short intervals 3-5 minutes HIIT",
                "Threshold": "threshold FTP 95-105% cruise intervals time trial sustained power",
                "Endurance": "endurance zone 2 60-75% FTP long steady aerobic base",
                "Recovery": "recovery easy spin 50-55% FTP active recovery",
                "Tempo": "tempo zone 3 76-87% FTP moderate sustained effort",
                "Anaerobic": "sprint anaerobic neuromuscular power 150%+ short bursts",
                "Force": "force SFR low cadence 50-60rpm strength big gear torque",
            }
            query_parts.append(type_enrichment.get(target_type, ""))

        search_query = " ".join(query_parts)

        # Search Qdrant with metadata filter: only workout documents (not books)
        results = self.kb.query(
            search_query,
            limit=limit * 3,
            score_threshold=0.50,
            metadata_filter={"type": "workout"}
        )

        # Parse workout info from text and deduplicate
        seen_names = set()
        similar_workouts = []

        for r in results:
            text = r["text"]
            score = r.get("score", 0)

            # Extract workout name from text (format: "# Zwift Workout: Name")
            name_match = re.search(r'# Zwift Workout:\s*(.+?)(?:\n|$)', text)
            workout_name = name_match.group(1).strip() if name_match else "Unknown"

            # Skip chunks without a proper workout name
            if workout_name == "Unknown":
                continue

            # Deduplicate by base name (remove "1. " prefix)
            base_name = re.sub(r'^\d+\.\s*', '', workout_name).strip()
            if base_name in seen_names:
                continue
            seen_names.add(base_name)

            # Extract metadata from embedded text
            category_match = re.search(r'\*\*Category\*\*:\s*(.+?)(?:\n|$)', text)
            duration_match = re.search(r'\*\*Duration\*\*:\s*(\d+)', text)
            tss_match = re.search(r'\*\*TSS\*\*:\s*([\d.]+)', text)
            if_match = re.search(r'\*\*IF\*\*:\s*([\d.]+)', text)
            focus_match = re.search(r'## Training Focus\n(.+?)(?:\n##|\Z)', text, re.DOTALL)
            structure_match = re.search(r'## Workout Structure\n(.+?)(?:\n##|\Z)', text, re.DOTALL)

            similar_workouts.append({
                'name': workout_name,
                'description': '',
                'duration': int(duration_match.group(1)) if duration_match else 0,
                'tss': float(tss_match.group(1)) if tss_match else 0,
                'intensity_factor': float(if_match.group(1)) if if_match else 0,
                'structure_summary': structure_match.group(1).strip()[:300] if structure_match else '',
                'training_focus': focus_match.group(1).strip()[:200] if focus_match else '',
                'category': category_match.group(1).strip() if category_match else '',
                'similarity_score': score,
            })

            if len(similar_workouts) >= limit:
                break

        return similar_workouts

    def plan_workout(self, state: AgentState) -> AgentState:
        """Plan the workout structure - Expert Coach with RAG-driven deep research"""
        target_type = state.get("target_workout_type", "")
        ftp = state["user_profile"].get("ftp", 250)

        # Get calculated power zones for this FTP
        zones_info = format_zones_for_prompt(ftp)
        target_zones = get_workout_type_zones(target_type, ftp) if target_type else {}

        # Retrieve similar Zwift workouts via semantic search in vector DB
        # Enrich query with theory concepts from RAG for better matches
        theory_keywords = ""
        if state.get("rag_context"):
            # Extract key concepts from first 2 RAG passages for enrichment
            rag_lines = state["rag_context"].split("\n")[:10]
            theory_keywords = " ".join(rag_lines)[:200]

        target_duration = state["user_profile"].get("typical_workout_duration", 60)
        similar_workouts = self.retrieve_similar_workouts(
            target_type=target_type,
            duration_minutes=target_duration,
            limit=5,
            theory_keywords=theory_keywords,
        )

        # Format similar workouts for prompt
        zwift_inspiration = ""
        if similar_workouts:
            zwift_inspiration = "\n== PROVEN WORKOUT STRUCTURES (from Zwift library) ==\n"
            zwift_inspiration += "These are real workouts that thousands of cyclists have completed. Use them for inspiration:\n\n"
            for i, w in enumerate(similar_workouts, 1):
                zwift_inspiration += f"{i}. **{w['name']}** ({w['category']})\n"
                zwift_inspiration += f"   Duration: {w['duration']}min | TSS: {w['tss']} | IF: {w['intensity_factor']}\n"
                if w['description']:
                    zwift_inspiration += f"   Description: {w['description']}\n"
                if w['training_focus']:
                    zwift_inspiration += f"   Focus: {w['training_focus']}\n"
                zwift_inspiration += f"   Structure: {w['structure_summary']}\n\n"

        planning_prompt = f"""
You are an EXPERT cycling coach with deep knowledge of training science.
Your mission: Create a UNIQUE, scientifically-grounded workout by doing DEEP RESEARCH in the training theory below.

== USER REQUEST ==
{state['user_input']}

== RIDER ANALYSIS ==
{state['messages'][-1].content}

== POWER ZONES (calculated for FTP={ftp:.0f}W) ==
{zones_info}

TARGET WORKOUT TYPE: {target_type}
RECOMMENDED ZONES: {target_zones.get('min_pct', 70)}-{target_zones.get('max_pct', 80)}% FTP ({target_zones.get('min_watts', 0):.0f}-{target_zones.get('max_watts', 0):.0f}W)
CP ZONE: {target_zones.get('cp_zone', 'See above')}

== TRAINING THEORY (from research - YOUR PRIMARY SOURCE!) ==
{state['rag_context']}

{zwift_inspiration}

== USER PREFERENCES (from past feedback) ==
{state.get('memory_context', 'No feedback history available.')}

=== CRITICAL WORKFLOW - READ CAREFULLY ===

Step 1: USE THE CALCULATED ZONES ABOVE
- You have the EXACT power zones calculated for this rider's FTP
- CP30 = {target_zones.get('min_pct', 88)}-{target_zones.get('max_pct', 93)}% FTP = {target_zones.get('min_watts', 0):.0f}-{target_zones.get('max_watts', 0):.0f}W
- When passages mention "CP30" or "CP60", use the calculated zones above
- NO GUESSING - the math is done for you

Step 2: DEEP RESEARCH IN TRAINING THEORY
- READ ALL passages to understand the PHYSIOLOGICAL PRINCIPLES
- Look for interval structures, durations, work/rest ratios mentioned
- Find EXAMPLES of workouts in the passages (e.g., "5x12min", "3x20min")
- Note cadence recommendations, especially for Force workouts

Step 3: CROSS-REFERENCE FOR HIGH CONFIDENCE
- Do 2+ passages mention similar structures? → Use that
- Passages marked "HIGH CONFIDENCE" or "Cross-validated" → Prioritize these
- Look for specific research citations → These are gold

Step 4: DESIGN UNIQUE WORKOUT
- Use the CALCULATED ZONES for intensity (no guessing!)
- Use INTERVAL STRUCTURES from the passages (durations, reps, rest)
- Combine principles creatively: e.g., "Passage 2 suggests 8-12min intervals, Passage 5 says progressive intensity works → 10min@88% + 12min@90%"
- Add variation: pyramids, over-unders, progressive, descending rest, etc.

Step 5: DOCUMENT CLEARLY
- RATIONALE: "Based on passage 3's recommendation of CP60 intervals (95-105% FTP from zones above) and passage 5's finding that..."
- Show which passages inspired which parts of the workout
- Reference the calculated zones when explaining intensity choices

== FITNESS STATE GUIDELINES ==
- TSB < -10: Recovery only (50-60% FTP)
- TSB -10 to 0: Endurance/Tempo
- TSB 0 to 5: Sweet Spot/Tempo/Threshold
- TSB > 5: VO2max/Anaerobic OK

REMEMBER: Every number in STRUCTURE must come from the training theory above!
Do NOT use generic zones - extract specific recommendations from the passages.
DURATION must be a number (minutes only, no text).
TSS must be a number (no text like "estimated").
IF must be a decimal number (e.g. 0.88).
"""

        # Use structured output for guaranteed field types
        structured_llm = self.llm.with_structured_output(WorkoutPlanOutput)
        response = structured_llm.invoke([HumanMessage(content=planning_prompt)])

        # Convert Pydantic model to dict
        plan = response.model_dump()
        state["workout_structure"] = plan

        state["reasoning"] += "=" * 60 + "\n"
        state["reasoning"] += "STEP 4: PLAN WORKOUT (LLM structured output)\n"
        state["reasoning"] += "=" * 60 + "\n\n"
        if similar_workouts:
            state["reasoning"] += f"INPUT - {len(similar_workouts)} similar Zwift workouts (Qdrant semantic search):\n"
            for w in similar_workouts:
                sim = w.get('similarity_score', 0)
                state["reasoning"] += f"  [{sim:.2f}] {w['name']} ({w['category']}) {w['duration']}min TSS={w['tss']}\n"
                if w.get('training_focus'):
                    state["reasoning"] += f"        focus: {w['training_focus'][:100]}\n"
                if w.get('structure_summary'):
                    state["reasoning"] += f"        structure: {w['structure_summary'][:150]}\n"
        else:
            state["reasoning"] += "INPUT - No similar Zwift workouts found in vector DB\n"
        state["reasoning"] += f"\nOUTPUT - Structured Plan (Pydantic guaranteed types):\n"
        for k, v in plan.items():
            if k != "intervals":
                display = str(v)[:120] + "..." if len(str(v)) > 120 else str(v)
                state["reasoning"] += f"  {k} ({type(v).__name__}): {display}\n"
        state["reasoning"] += "\n"

        # Add plan summary as message for next step
        plan_summary = f"NAME: {plan['NAME']}\nTYPE: {plan['TYPE']}\nSTRUCTURE: {plan['STRUCTURE']}"
        state["messages"].append(SystemMessage(content=plan_summary))

        return state

    def generate_structure(self, state: AgentState) -> AgentState:
        """Generate detailed workout structure with specific intervals"""
        plan = state["workout_structure"]
        ftp = state["user_profile"].get("ftp", 250)
        workout_type = plan.get("TYPE", state.get("target_workout_type", ""))

        # Get adaptive warmup
        warmup_instruction = self.WARMUP_STYLES.get(
            workout_type,
            "Warmup (10-15 min, gradual ramp from 0.50 to 0.70)"
        )

        cadence_notes = plan.get("CADENCE_NOTES", "")

        structure_prompt = f"""
Convert this workout plan into a detailed interval structure:

Workout Plan:
{plan.get('STRUCTURE', 'intervals')}

Workout Type: {workout_type}
FTP: {ftp}W
Total Duration: {plan.get('DURATION', 90)} minutes
{f"Cadence targets: {cadence_notes}" if cadence_notes else ""}

CRITICAL - Convert the workout plan above into intervals:
- Follow the power percentages specified in the workout plan EXACTLY
- If the plan says "75-85% FTP", use values in that range (e.g., 0.75-0.85)
- If the plan says "low cadence 50-60rpm", include that in the output
- The workout plan was designed based on training science, so trust its intensity specifications

Typical power zones for reference (but follow the plan above):
- Recovery: 0.50-0.55, Endurance: 0.56-0.75, Tempo: 0.76-0.90
- Sweet Spot: 0.88-0.93, Threshold: 0.94-1.05, VO2max: 1.06-1.20, Anaerobic: 1.21+

Create a complete workout with:
1. {warmup_instruction}
2. Main intervals (MUST match the workout type's power zone and the plan above!)
3. Cooldown (10 min, ramp from 0.55 to 0.45)

If the plan mentions specific cadence targets (SFR, high cadence drills, sprints),
you MUST include cadence values in the output.

Output format (one per line, cadence is optional):
WARMUP: duration_seconds, start_power_%, end_power_%, [cadence_rpm]
INTERVAL: duration_seconds, power_%, repeat_count, rest_duration_seconds, rest_power_%, [cadence_on_rpm], [cadence_off_rpm]
STEADYSTATE: duration_seconds, power_%, [cadence_rpm]
COOLDOWN: duration_seconds, start_power_%, end_power_%, [cadence_rpm]

Examples:

Sweet Spot Over-Under:
WARMUP: 600, 0.50, 0.70
INTERVAL: 180, 0.95, 4, 180, 0.85, 90, 85
STEADYSTATE: 180, 0.55
INTERVAL: 180, 0.95, 4, 180, 0.85, 90, 85
COOLDOWN: 600, 0.55, 0.45

VO2max Billats 30/30:
WARMUP: 900, 0.50, 0.75
INTERVAL: 30, 1.20, 10, 30, 0.55, 100, 85
STEADYSTATE: 300, 0.55
INTERVAL: 30, 1.20, 10, 30, 0.55, 100, 85
COOLDOWN: 600, 0.55, 0.45

SFR Force (low cadence):
WARMUP: 900, 0.50, 0.70
INTERVAL: 300, 0.80, 6, 300, 0.55, 55, 90
COOLDOWN: 600, 0.55, 0.45

Recovery:
WARMUP: 600, 0.45, 0.55, 90
STEADYSTATE: 2400, 0.52, 90
COOLDOWN: 600, 0.52, 0.45, 85
"""

        response = self.llm.invoke([HumanMessage(content=structure_prompt)])

        state["workout_structure"]["intervals"] = response.content

        state["reasoning"] += "=" * 60 + "\n"
        state["reasoning"] += "STEP 5: GENERATE STRUCTURE (intervals)\n"
        state["reasoning"] += "=" * 60 + "\n\n"
        state["reasoning"] += f"INPUT - Warmup style: {warmup_instruction[:80]}\n"
        state["reasoning"] += f"INPUT - Plan structure: {plan.get('STRUCTURE', 'N/A')[:120]}\n\n"
        state["reasoning"] += f"OUTPUT - Raw interval lines:\n{response.content}\n\n"

        # Show parsed intervals for verification
        parsed = self._parse_intervals(response.content)
        state["reasoning"] += f"PARSED - {len(parsed)} intervals recognized:\n"
        for p in parsed:
            state["reasoning"] += f"  {p}\n"
        state["reasoning"] += "\n"

        return state

    def format_zwo(self, state: AgentState) -> AgentState:
        """Format workout as .zwo XML file"""
        from src.agent.zwo_generator import ZwoGenerator

        plan = state["workout_structure"]
        generator = ZwoGenerator()

        # Parse intervals from LLM output
        intervals = self._parse_intervals(plan.get("intervals", ""))

        zwo_xml = generator.generate_zwo(
            name=plan.get("NAME", "Workout"),
            description=f"TSS: {plan.get('TSS', 'N/A')}, IF: {plan.get('IF', 'N/A')}\n{plan.get('RATIONALE', '')}",
            intervals=intervals
        )

        state["workout_xml"] = zwo_xml
        return state

    def _format_recent_activities(self, activities: list) -> str:
        """Format recent activities for prompt"""
        if not activities:
            return "No recent activities"

        lines = []
        for act in activities[-7:]:
            lines.append(
                f"- {act.get('date')}: {act.get('name')} - {act.get('duration')}min, "
                f"TSS: {act.get('tss', 'N/A')}"
            )
        return "\n".join(lines)

    def _parse_workout_plan(self, content: str) -> dict:
        """Parse LLM workout plan response - handles markdown formatting"""
        import re
        plan = {}
        valid_keys = {"NAME", "TYPE", "DURATION", "TSS", "IF", "STRUCTURE", "RATIONALE", "CADENCE_NOTES"}

        # Try to find each key explicitly, handling markdown like **NAME**: or - NAME:
        for key in valid_keys:
            # Match patterns like: NAME: value, **NAME**: value, **NAME:** value, - NAME: value
            pattern = rf'(?:^|\n)\s*[-*]*\s*\**{key}\**\s*:\s*(.+?)(?=\n\s*[-*]*\s*\**(?:{"|".join(valid_keys)})\**\s*:|\Z)'
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                # Clean markdown artifacts
                value = re.sub(r'^\*+|\*+$', '', value).strip()
                # For single-line fields, take only first line
                if key in {"NAME", "TYPE", "DURATION", "TSS", "IF"}:
                    value = value.split("\n")[0].strip()
                    # Remove units like "90 minutes" -> "90"
                    if key == "DURATION":
                        duration_match = re.search(r'(\d+)', value)
                        if duration_match:
                            value = duration_match.group(1)
                plan[key] = value

        return plan

    def _parse_intervals(self, intervals_text: str) -> list:
        """Parse interval structure from LLM output"""
        intervals = []

        for line in intervals_text.split("\n"):
            line = line.strip()
            if not line:
                continue

            try:
                if line.startswith("WARMUP:"):
                    parts = line.replace("WARMUP:", "").split(",")
                    interval_data = {
                        "type": "warmup",
                        "duration": int(parts[0].strip()),
                        "power_start": float(parts[1].strip()),
                        "power_end": float(parts[2].strip()),
                    }
                    if len(parts) > 3:
                        interval_data["cadence"] = int(parts[3].strip())
                    intervals.append(interval_data)

                elif line.startswith("INTERVAL:"):
                    parts = line.replace("INTERVAL:", "").split(",")
                    interval_data = {
                        "type": "intervals",
                        "on_duration": int(parts[0].strip()),
                        "on_power": float(parts[1].strip()),
                        "repeat": int(parts[2].strip()),
                        "off_duration": int(parts[3].strip()),
                        "off_power": float(parts[4].strip()),
                    }
                    if len(parts) > 5:
                        interval_data["cadence_on"] = int(parts[5].strip())
                    if len(parts) > 6:
                        interval_data["cadence_off"] = int(parts[6].strip())
                    intervals.append(interval_data)

                elif line.startswith("STEADYSTATE:"):
                    parts = line.replace("STEADYSTATE:", "").split(",")
                    interval_data = {
                        "type": "steadystate",
                        "duration": int(parts[0].strip()),
                        "power": float(parts[1].strip()),
                    }
                    if len(parts) > 2:
                        interval_data["cadence"] = int(parts[2].strip())
                    intervals.append(interval_data)

                elif line.startswith("COOLDOWN:"):
                    parts = line.replace("COOLDOWN:", "").split(",")
                    interval_data = {
                        "type": "cooldown",
                        "duration": int(parts[0].strip()),
                        "power_start": float(parts[1].strip()),
                        "power_end": float(parts[2].strip()),
                    }
                    if len(parts) > 3:
                        interval_data["cadence"] = int(parts[3].strip())
                    intervals.append(interval_data)
            except (ValueError, IndexError) as e:
                print(f"Warning: Could not parse interval line: {line} - {e}")
                continue

        return intervals

    def _format_feedback_history(self, feedbacks: list) -> str:
        """Format feedback history grouped by relevance to current workout type"""
        if not feedbacks:
            return "No previous feedback"

        same_type = [fb for fb in feedbacks if fb.get("is_same_type", False)]
        other_type = [fb for fb in feedbacks if not fb.get("is_same_type", False)]

        lines = []
        if same_type:
            lines.append("=== FEEDBACK FOR THIS WORKOUT TYPE (MOST RELEVANT - use for intensity/structure adjustments) ===")
            for fb in same_type:
                workout_name = fb.get("workout_name", "Unknown")
                wtype = fb.get("workout_type", "Unknown")
                difficulty = fb.get("difficulty", "N/A")
                rating = fb.get("rating", "N/A")
                notes = fb.get("notes", "")
                lines.append(f"- [{wtype}] {workout_name}: Difficulty={difficulty}, Rating={rating}/5")
                if notes:
                    lines.append(f"  Notes: {notes}")

        if other_type:
            lines.append("\n=== GENERAL FEEDBACK (other workout types - only use for general preferences, NOT intensity) ===")
            for fb in other_type:
                workout_name = fb.get("workout_name", "Unknown")
                wtype = fb.get("workout_type", "Unknown")
                difficulty = fb.get("difficulty", "N/A")
                rating = fb.get("rating", "N/A")
                notes = fb.get("notes", "")
                lines.append(f"- [{wtype}] {workout_name}: Difficulty={difficulty}, Rating={rating}/5")
                if notes:
                    lines.append(f"  Notes: {notes}")

        return "\n".join(lines)

    def generate_workout(
        self,
        user_input: str,
        user_profile: dict,
        training_history: list,
        feedback_history: list = None
    ) -> dict:
        """
        Generate a complete workout

        Args:
            user_input: User's workout request (e.g., "1 hour sweet spot")
            user_profile: Dict with ftp, ctl, atl, tsb, target_workout_type
            training_history: List of recent activities
            feedback_history: List of feedback dicts with is_same_type flag

        Returns:
            Dict with workout_xml, reasoning, structure
        """
        target_type = user_profile.get("target_workout_type", "")

        initial_state = AgentState(
            messages=[],
            user_input=user_input,
            user_profile=user_profile,
            training_history=training_history,
            user_feedback_history=feedback_history or [],
            rag_context="",
            memory_context="",
            workout_structure={},
            workout_xml="",
            reasoning="",
            target_workout_type=target_type,
        )

        # Run graph
        final_state = self.graph.invoke(initial_state)

        return {
            "workout_xml": final_state["workout_xml"],
            "reasoning": final_state["reasoning"],
            "structure": final_state["workout_structure"],
        }
