"""
LangGraph Agent for Workout Generation
"""
from typing import TypedDict, Annotated, Sequence, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from config import settings
from src.rag.knowledge_base import KnowledgeBase
import operator


# Agent State
class AgentState(TypedDict):
    """State of the workout generation agent"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    user_input: str
    user_profile: dict  # FTP, CTL, ATL, TSB
    training_history: list  # Recent activities
    rag_context: str
    workout_structure: dict
    workout_xml: str
    reasoning: str


class WorkoutAgent:
    """LangGraph agent for generating personalized cycling workouts"""

    def __init__(self):
        self.kb = KnowledgeBase()
        self.llm = ChatOpenAI(
            model="gpt-4o",
            api_key=settings.openai_api_key,  # Will use ANTHROPIC_API_KEY env var
            temperature=0.7,
        )

        # Build graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow"""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("analyze_rider", self.analyze_rider)
        workflow.add_node("retrieve_theory", self.retrieve_theory)
        workflow.add_node("plan_workout", self.plan_workout)
        workflow.add_node("generate_structure", self.generate_structure)
        workflow.add_node("format_zwo", self.format_zwo)

        # Define edges
        workflow.set_entry_point("analyze_rider")
        workflow.add_edge("analyze_rider", "retrieve_theory")
        workflow.add_edge("retrieve_theory", "plan_workout")
        workflow.add_edge("plan_workout", "generate_structure")
        workflow.add_edge("generate_structure", "format_zwo")
        workflow.add_edge("format_zwo", END)

        return workflow.compile()

    def analyze_rider(self, state: AgentState) -> AgentState:
        """Analyze rider's current fitness and fatigue"""
        profile = state["user_profile"]
        history = state["training_history"]

        # Build analysis prompt
        analysis_prompt = f"""
Analyze this cyclist's current state:

Profile:
- FTP: {profile.get('ftp')} watts
- CTL (Fitness): {profile.get('ctl')}
- ATL (Fatigue): {profile.get('atl')}
- TSB (Form): {profile.get('tsb')}

Recent Training (last 7 days):
{self._format_recent_activities(history)}

Based on TSB:
- TSB > 5: Fresh, can handle hard workouts
- TSB -10 to 5: Optimal training zone
- TSB < -10: Fatigued, need recovery

Provide a 2-sentence analysis of their current state and what type of workout is appropriate.
"""

        response = self.llm.invoke([HumanMessage(content=analysis_prompt)])

        state["reasoning"] = f"Rider Analysis:\n{response.content}\n\n"
        state["messages"] = [SystemMessage(content=response.content)]

        return state

    def retrieve_theory(self, state: AgentState) -> AgentState:
        """Retrieve relevant training theory from RAG"""
        user_input = state["user_input"]

        # Query knowledge base
        results = self.kb.query(
            f"Training theory for: {user_input}. Focus on power zones, intervals, and workout structure.",
            limit=3
        )

        # Build context
        context = "Relevant Training Theory:\n\n"
        for i, result in enumerate(results):
            context += f"{i+1}. {result['text'][:300]}...\n\n"

        state["rag_context"] = context
        state["reasoning"] += f"Retrieved Knowledge:\n{len(results)} relevant passages found\n\n"

        return state

    def plan_workout(self, state: AgentState) -> AgentState:
        """Plan the workout structure based on user input and analysis"""
        planning_prompt = f"""
You are an expert cycling coach. Plan a workout based on:

User Request: {state['user_input']}

{state['messages'][-1].content}

{state['rag_context']}

Create a workout plan with:
1. Workout name (concise, e.g., "Sweet Spot 3x12")
2. Workout type (Recovery, Endurance, Tempo, Sweet Spot, Threshold, VO2max, Anaerobic)
3. Total duration (minutes)
4. Target TSS
5. Intensity Factor (IF)
6. Main intervals structure (how many sets, duration, power %)

Respond in this exact format:
NAME: [workout name]
TYPE: [workout type]
DURATION: [total minutes]
TSS: [estimated TSS]
IF: [estimated IF]
STRUCTURE: [detailed interval structure]
RATIONALE: [Why this workout is appropriate given their current fitness]
"""

        response = self.llm.invoke([HumanMessage(content=planning_prompt)])

        # Parse response
        plan = self._parse_workout_plan(response.content)
        state["workout_structure"] = plan
        state["reasoning"] += f"Workout Plan:\n{response.content}\n\n"
        state["messages"].append(response)

        return state

    def generate_structure(self, state: AgentState) -> AgentState:
        """Generate detailed workout structure with specific intervals"""
        plan = state["workout_structure"]
        ftp = state["user_profile"].get("ftp", 250)

        structure_prompt = f"""
Convert this workout plan into a detailed interval structure:

{plan.get('STRUCTURE', 'Sweet spot intervals')}

FTP: {ftp}W
Total Duration: {plan.get('DURATION', 90)} minutes

Create a complete workout with:
1. Warmup (10-15 min, gradual ramp from 50% to 70% FTP)
2. Main intervals (as specified in plan)
3. Cooldown (10 min, 50-60% FTP)

Output format (one per line):
WARMUP: duration_seconds, start_power_%, end_power_%
INTERVAL: duration_seconds, power_%, repeat_count, rest_duration_seconds, rest_power_%
STEADYSTATE: duration_seconds, power_%
COOLDOWN: duration_seconds, start_power_%, end_power_%

Example:
WARMUP: 600, 0.50, 0.70
INTERVAL: 720, 0.90, 3, 300, 0.55
COOLDOWN: 600, 0.60, 0.50
"""

        response = self.llm.invoke([HumanMessage(content=structure_prompt)])

        state["workout_structure"]["intervals"] = response.content
        state["reasoning"] += f"Interval Structure:\n{response.content}\n\n"

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
        for act in activities[-7:]:  # Last 7
            lines.append(
                f"- {act.get('date')}: {act.get('name')} - {act.get('duration')}min, "
                f"TSS: {act.get('tss', 'N/A')}"
            )
        return "\n".join(lines)

    def _parse_workout_plan(self, content: str) -> dict:
        """Parse LLM workout plan response"""
        plan = {}
        for line in content.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                plan[key.strip()] = value.strip()
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
                    intervals.append({
                        "type": "warmup",
                        "duration": int(parts[0].strip()),
                        "power_start": float(parts[1].strip()),
                        "power_end": float(parts[2].strip()),
                    })

                elif line.startswith("INTERVAL:"):
                    parts = line.replace("INTERVAL:", "").split(",")
                    intervals.append({
                        "type": "intervals",
                        "on_duration": int(parts[0].strip()),
                        "on_power": float(parts[1].strip()),
                        "repeat": int(parts[2].strip()),
                        "off_duration": int(parts[3].strip()),
                        "off_power": float(parts[4].strip()),
                    })

                elif line.startswith("STEADYSTATE:"):
                    parts = line.replace("STEADYSTATE:", "").split(",")
                    intervals.append({
                        "type": "steadystate",
                        "duration": int(parts[0].strip()),
                        "power": float(parts[1].strip()),
                    })

                elif line.startswith("COOLDOWN:"):
                    parts = line.replace("COOLDOWN:", "").split(",")
                    intervals.append({
                        "type": "cooldown",
                        "duration": int(parts[0].strip()),
                        "power_start": float(parts[1].strip()),
                        "power_end": float(parts[2].strip()),
                    })
            except (ValueError, IndexError) as e:
                print(f"Warning: Could not parse interval line: {line} - {e}")
                continue

        return intervals

    def generate_workout(
        self,
        user_input: str,
        user_profile: dict,
        training_history: list
    ) -> dict:
        """
        Generate a complete workout

        Args:
            user_input: User's workout request (e.g., "1 hour sweet spot")
            user_profile: Dict with ftp, ctl, atl, tsb
            training_history: List of recent activities

        Returns:
            Dict with workout_xml, reasoning, structure
        """
        initial_state = AgentState(
            messages=[],
            user_input=user_input,
            user_profile=user_profile,
            training_history=training_history,
            rag_context="",
            workout_structure={},
            workout_xml="",
            reasoning=""
        )

        # Run graph
        final_state = self.graph.invoke(initial_state)

        return {
            "workout_xml": final_state["workout_xml"],
            "reasoning": final_state["reasoning"],
            "structure": final_state["workout_structure"],
        }
