# Claude Project: AI Cycling Coach

## Project Overview
Agent LangGraph/CrewAI pour générer des programmes d'entraînement vélo personnalisés avec structured outputs (.zwo compatible Zwift/Wahoo). Alternative gratuite à TrainerRoad avec flexibilité maximale.

## Core Features

### 1. Knowledge Base (RAG)
- **Sources**: Livres d'entraînement cycliste (Training and Racing with a Power Meter, The Cyclist's Training Bible, etc.)
- **Vector DB**: Pinecone/Qdrant pour embeddings
- **Retrieval**: Contexte théorique TSS, zones, périodisation, intervalles

### 2. Data Integration
- **Strava API**: Récup historique complet + rolling 3 mois
- **Metrics clés**: 
  - FTP actuel
  - TSS hebdo/mensuel
  - Distribution intensité (Z1-Z7)
  - Fatigue/forme (CTL/ATL/TSB)
  - Type d'efforts (endurance, tempo, seuil, VO2max, anaérobie)

### 3. Agent Architecture (LangGraph) - Dual Agent System

**ARCHITECTURE FINALE : 2 agents spécialisés**

#### WorkoutAgent (Tacticien) - Génération de séances individuelles
```python
# Flow WorkoutAgent (6 nodes)
AgentState: {
    user_profile,           # FTP, CTL, ATL, TSB, target_workout_type
    training_history,
    user_feedback_history,  # Type-aware feedback
    rag_context,
    memory_context,
    workout_structure,
    workout_xml,
    reasoning,
    target_workout_type
}

Nodes:
1. analyze_rider → profil actuel (CTL, TSB, forces/faiblesses)
2. retrieve_memory → feedback contextualisé PAR TYPE (Recovery feedback ≠ VO2max feedback)
3. retrieve_theory → RAG multi-query adaptatif (4 queries: user + 2 type-specific + 1 fitness-state)
4. plan_workout → Expert coach créatif (52 styles d'intervalles, échantillonnage aléatoire)
5. generate_structure → Conversion en intervalles détaillés + cadence targets
6. format_zwo → XML generation (.zwo compatible Zwift/Wahoo)

COACHING_KNOWLEDGE:
- 8 catégories: Endurance, Sweet Spot, Threshold, VO2max, Anaerobic, Force, Recovery, Tempo
- 52 styles d'intervalles: Billats 30/30, micro-bursts, over-unders, SFR, pyramids, etc.
- Adaptive warmups par type (openers pour VO2max, low cadence prep pour Force)
- Cadence management (high/low cadence drills intégrés dans .zwo)
```

#### PlanAgent (Stratégiste) - Planification macro long terme
```python
# Flow PlanAgent (6 nodes)
PlanState: {
    user_profile,
    training_history,
    user_feedback_history,
    goal,              # target_ftp, target_date, hours_per_week, sessions_per_week
    rag_context,       # Periodization theory
    macro_plan,        # Full JSON macro plan
    week_detail,       # Current week being planned
    reasoning
}

Nodes:
1. parse_goal → Parse objectif (FTP target, race prep, base building) + validation timeline
2. analyze_current_fitness → Analyse 90j trends, zone distribution, forces/faiblesses
3. retrieve_periodization_theory → RAG theory (periodization, peaking, tapering, progressive overload)
4. design_macro_plan → Crée plan macro (Base→Build→Peak→Taper, TSS/semaine, zone focus)
5. plan_current_week → Planifie semaine avec adaptations (fatigue, compliance, CTL ramp)
6. distribute_workouts → Répartit TSS hebdo sur N séances avec séquençage (hard-easy-hard pattern)

Two entry points:
- create_program() → Full 6-node graph (création programme complet)
- plan_week() → Nodes 5-6 only (re-planification hebdo avec adaptations)
```

#### AdaptationEngine (Moteur adaptatif déterministe)
```python
# Logique d'adaptation entre PlanAgent et WorkoutAgent
Rules:
1. TSB < -20 → Force recovery week (TSS × 0.5)
2. TSB < -10 → Reduce load 15% (TSS × 0.85)
3. Compliance < 70% (2+ weeks) → Reduce targets 20%
4. CTL ramp > 7 TSS/day → Back off 10%
5. Recovery week every 3-4 weeks (TSS × 0.6)

Methods:
- analyze_compliance() → Compare planned vs actual
- calculate_adjustments() → Determine TSS multipliers
- detect_overtraining_risk() → Risk levels (none/low/medium/high)
- recommend_recovery_week() → Timing logic
- adjust_week_distribution() → Session sequencing
```

#### Workout Bridge (Pont entre agents)
```python
# src/agent/workout_bridge.py
generate_planned_workout(planned_workout, user_profile, history, feedback):
    """
    Traduit contraintes PlanAgent → WorkoutAgent

    Input: PlannedWorkout (type, TSS target, duration, instructions)
    Output: .zwo file via WorkoutAgent
    Validation: ±15% tolerance sur TSS/durée
    """

Flow complet:
PlanAgent → PlannedWorkout DB → User clicks "Generate" → workout_bridge → WorkoutAgent → .zwo file
```

### 4. Memory System
- **ConversationBufferMemory**: Retenir feedbacks user ("trop dur", "parfait", "plus de sweet spot")
- **User Profile Store**: 
  - Préférences intensité
  - Réponse à certains types d'entraînement
  - Disponibilités récurrentes
  - Historique ajustements
- **Adaptation**: L'agent apprend patterns individuels

### 5. Structured Output (.zwo)

```xml
<workout_file>
    <name>Sweet Spot 3x12</name>
    <description>TSS: 85, IF: 0.88</description>
    <workout>
        <SteadyState Duration="600" Power="0.65"/>  <!-- Warmup -->
        <IntervalsT Repeat="3" OnDuration="720" OffDuration="300" 
                    OnPower="0.90" OffPower="0.55"/>
        <SteadyState Duration="600" Power="0.55"/>  <!-- Cooldown -->
    </workout>
</workout_file>
```

**Zones calculées auto** depuis FTP:
- Z1: <55% - Recovery
- Z2: 56-75% - Endurance
- Z3: 76-90% - Tempo
- Z4: 91-105% - Threshold
- Z5: 106-120% - VO2max
- Z6: 121-150% - Anaerobic
- Z7: >150% - Neuromuscular

### 6. Training Theory Implementation

**Calculs automatiques**:
- **TSS**: (duration × NP × IF) / (FTP × 3600) × 100
- **IF**: NP / FTP
- **CTL** (Chronic Training Load): moyenne mobile 42j du TSS
- **ATL** (Acute Training Load): moyenne mobile 7j du TSS
- **TSB** (Training Stress Balance): CTL - ATL

**Logique périodisation**:
- Base → Build → Peak → Taper selon deadline
- Respect surcharge progressive (+5-10% TSS/semaine max)
- Recovery weeks (TSS -40% chaque 3-4 semaines)

### 7. Use Cases

**Programme court** (1-2 semaines):
```
Input: "J'ai une course dans 10 jours, je veux affûter"
Output: Taper plan avec opener workouts + .zwo files
```

**Programme long** (12-24 semaines):
```
Input: "Objectif 300W FTP dans 4 mois, actuellement 265W"
Output: Mesocycle structuré, progression TSS, focus zones changeantes
```

**Séance ad-hoc**:
```
Input: "1h15 dispo demain, envie de sweet spot"
Output: Single .zwo optimisé selon fatigue actuelle (TSB)
```

## Tech Stack

**Core**:
- LangGraph (orchestration) ou CrewAI (si multi-agents)
- Openai (reasoning + structured outputs)
- Langchain (RAG pipeline)

**Storage**:
- Qdrant/Pinecone (vector DB livres)
- SQLite/Postgres (user profiles, training history)

**Integration**:
- Strava API (OAuth + data fetch)
- XML generation (lxml/ElementTree pour .zwo)

**Memory**:
- Langchain Memory modules
- Custom user adaptation layer

**UI**:
- Streamlit (interface simple, rapide à dev)

## Streamlit UI Structure

### Pages principales

**1. 🏠 Dashboard**
```python
# Metrics row
col1, col2, col3, col4 = st.columns(4)
col1.metric("FTP", "265W", "+5W")
col2.metric("CTL", "85", "+2")
col3.metric("TSB", "-15", "🔴 Fatigué")
col4.metric("7d TSS", "450", "+10%")

# Charts
- Line chart: CTL/ATL/TSB last 90 days
- Bar chart: Weekly TSS distribution
- Pie chart: Zone distribution (Z1-Z7)
```

**2. 🎯 Generate Workout**
```python
# Input section
workout_type = st.selectbox("Type", ["Single Workout", "Weekly Plan", "Full Program"])

if workout_type == "Single Workout":
    duration = st.slider("Duration (min)", 30, 180, 90)
    focus = st.selectbox("Focus", ["Endurance", "Sweet Spot", "Threshold", "VO2max", "Recovery"])
    
if workout_type == "Full Program":
    target_ftp = st.number_input("Target FTP", value=280)
    deadline = st.date_input("Target Date")
    weekly_hours = st.slider("Hours/week available", 5, 20, 10)

# Generate button
if st.button("Generate 🚴"):
    with st.spinner("Agent thinking..."):
        # LangGraph agent call
        result = agent.invoke(...)
        
    st.success("Workout generated!")
    st.download_button("Download .zwo", data=zwo_file, file_name="workout.zwo")
    
    # Preview
    st.subheader("Workout Preview")
    # Visualization des intervalles (plotly timeline)
    # Rationale de l'agent
```

**3. 📚 Training Library**
```python
# Saved workouts
df_workouts = pd.DataFrame(past_workouts)
st.dataframe(df_workouts[["Name", "TSS", "Duration", "Focus", "Date"]])

# Filter/search
search = st.text_input("Search workouts...")
filter_zone = st.multiselect("Filter by zone", ["Z2", "Z3", "Z4", "Z5"])
```

**4. 📊 Analytics**
```python
# Strava sync status
if st.button("Sync Strava"):
    fetch_strava_data()
    st.success("Synced!")

# Training load trends
st.plotly_chart(ctl_atl_chart)

# Power curve (best efforts 5s, 1min, 5min, 20min, 60min)
st.plotly_chart(power_curve)

# Zone time distribution heatmap
```

**5. ⚙️ Settings**
```python
# User profile
ftp = st.number_input("Current FTP", value=265)
weight = st.number_input("Weight (kg)", value=72)

# Preferences
st.subheader("Training Preferences")
preferred_duration = st.slider("Typical workout duration", 60, 180, 90)
recovery_preference = st.select_slider("Recovery intensity", ["Easy", "Moderate", "Hard"])

# Memory/feedback
st.subheader("Agent Memory")
st.text_area("Notes for the agent", "e.g., I prefer longer intervals, don't like short VO2 reps")
```

**6. 📅 Training Program** (NEW - Phase 4 IMPLEMENTED)
```python
# Three views: List/Create, Overview, Week Detail

## VIEW A: Program Creation Form
goal_type = st.selectbox("Goal", ["Increase FTP", "Prepare for race", "Build base"])
target_ftp = st.number_input("Target FTP", value=current_ftp + 30)
target_date = st.date_input("Target Date", min=4 weeks, max=24 weeks)
hours_per_week = st.slider("Hours/week", 4, 20, 10)
sessions_per_week = st.slider("Sessions/week", 3, 7, 5)

# PlanAgent creates full program (30-60s generation time)

## VIEW B: Program Overview (Macro View)
- Progress: weeks completed / total, FTP current vs target, days remaining
- Phase timeline: horizontal bar chart (Base→Build→Peak→Taper with colors)
- Weekly TSS chart: planned (outline) vs actual (filled) bars by phase
- CTL progression: projected (dashed) vs actual (solid) line chart
- "View Current Week" button → transitions to Week Detail

## VIEW C: Week Detail (Workout Management)
- Week summary: Target TSS, zone focus, coaching notes, adaptation notes
- Workout cards list:
  [Workout 1: Sweet Spot | 90min | TSS ~75 | Status: Planned]
     [Generate .zwo] ← Calls WorkoutAgent via workout_bridge
  [Workout 2: VO2max | 60min | TSS ~65 | Status: Generated]
     [Download .zwo] [Re-generate] [Give Feedback]
  [Workout 3: Recovery | 60min | TSS ~30 | Status: Completed]
     [Download .zwo] [View Feedback]
- "Re-plan This Week" button → calls PlanAgent.plan_week() with adaptation

# Weekly Re-Planning Flow (Adaptive)
1. User completes week → Strava sync populates actual_tss, actual_ctl, actual_tsb
2. User navigates to next week → auto-triggers plan_week() if not already planned
3. AdaptationEngine checks: TSB, compliance, CTL ramp → adjusts TSS
4. PlanAgent generates adapted week (nodes 5-6)
5. Workouts distributed across sessions with proper sequencing
```

### Components réutilisables

```python
# components/workout_card.py
def render_workout_card(workout):
    with st.container():
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.write(f"**{workout.name}**")
        col2.metric("TSS", workout.tss)
        col3.metric("IF", workout.intensity_factor)
        
        # Expandable details
        with st.expander("Details"):
            st.write(workout.description)
            # Timeline visualization
            st.plotly_chart(create_interval_chart(workout))

# components/metrics_dashboard.py
def render_fitness_metrics(user_data):
    # PMC chart (Performance Management Chart)
    # CTL/ATL/TSB visualization
    pass

# components/agent_chat.py
def render_agent_conversation():
    # Chat interface with memory
    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])
    
    if prompt := st.chat_input():
        response = agent.chat(prompt)
        st.chat_message("assistant").write(response)
```

### Session State Management

```python
# Initialize
if 'user_profile' not in st.session_state:
    st.session_state.user_profile = load_user_profile()
if 'agent_memory' not in st.session_state:
    st.session_state.agent_memory = []
if 'current_workout' not in st.session_state:
    st.session_state.current_workout = None

# Persist across reruns
@st.cache_resource
def get_agent():
    return initialize_langgraph_agent()

@st.cache_data(ttl=3600)
def get_strava_data(user_id):
    return fetch_from_strava(user_id)
```

## Workflow Type User

1. **Onboarding**: 
   - Connect Strava (OAuth flow dans Streamlit)
   - Fetch 6 mois data → Calculer FTP/zones
   - Set initial preferences
   
2. **Set Goal**: 
   - Page "Generate Workout"
   - Sélection type + inputs
   - "Je veux 280W FTP pour juin" ou "Séance 90min demain"
   
3. **Agent Processing**:
   - Spinner "Thinking..."
   - Query RAG théorie pertinente
   - Analyse training load actuel
   - Check mémoire préférences user
   - Generate plan/workout
   
4. **Output**: 
   - Preview workout dans UI (timeline Plotly)
   - Download .zwo button
   - Rationale expander (pourquoi ce TSS, cette intensité)
   
5. **Feedback Loop**: 
   - Après workout: thumbs up/down + notes
   - "trop facile" → Adjust future generations
   - Agent memory update

## Avantages vs TrainerRoad

✅ **Gratuit**  
✅ **Fully customizable** (durées, intensités)  
✅ **Apprend de toi** (memory)  
✅ **Théorie accessible** (RAG explique pourquoi)  
✅ **Programs courts ET longs**  
✅ **Compatible Zwift + Wahoo natif**  
✅ **UI simple mais efficace** (Streamlit)

## Development Phases

### Phase 1: Foundation (Week 1-2)
- Setup RAG pipeline (Qdrant + embeddings livres vélo)
- Strava API integration basique
- SQLite user profiles
- Streamlit skeleton (Dashboard + Settings)

### Phase 2: Core Agent (Week 3-4)
- LangGraph agent (single workout generation)
- .zwo structured output
- TSS/IF/zones calculations
- Streamlit "Generate Workout" page

### Phase 3: Intelligence (Week 5-6)
- Memory layer implementation
- User adaptation logic
- Analytics page (charts CTL/ATL/TSB)
- Workout library

### Phase 4: Advanced ✅ COMPLETED
- ✅ Long-term planning (PlanAgent avec 6 nodes)
- ✅ Multi-week program generation (4-24 semaines)
- ✅ Advanced RAG queries (periodization theory, multi-query adaptive)
- ✅ AdaptationEngine (compliance, TSB, CTL ramp monitoring)
- ✅ Training Program page (3 views: create, overview, week detail)
- ✅ Database models (TrainingProgram, WeekPlan, PlannedWorkout)
- ✅ Workout bridge (PlanAgent ↔ WorkoutAgent integration)
- ✅ Program visualizations (timeline, TSS planned vs actual, CTL progression)

### Phase 5: Production (En cours)
- 🔄 Testing end-to-end (programmes longs)
- ⏳ Edge cases: pause program, mid-program FTP update, Strava activity matching
- ⏳ Error handling amélioré
- ⏳ Documentation utilisateur
- ⏳ Deploy (Streamlit Cloud ou self-hosted)

---

## Architecture Complète - Fichiers Clés

### Agents
- **`src/agent/workout_agent.py`** (450 lignes) - WorkoutAgent LangGraph 6 nodes, 52 styles d'intervalles, type-aware feedback, multi-query RAG, cadence support
- **`src/agent/plan_agent.py`** (500 lignes) - PlanAgent LangGraph 6 nodes, macro periodization, weekly re-planning, adaptation logic
- **`src/agent/adaptation.py`** (240 lignes) - AdaptationEngine déterministe (compliance, TSB guards, CTL ramp, recovery timing)
- **`src/agent/workout_bridge.py`** (160 lignes) - Pont PlanAgent ↔ WorkoutAgent, constraint validation (±15% tolerance)
- **`src/agent/zwo_generator.py`** - XML .zwo generation avec cadence targets

### Database
- **`src/database/models.py`** (290 lignes) - 10 modèles SQLAlchemy:
  - User, UserProfile, UserPreference, Activity, WorkoutPlan, WorkoutFeedback
  - **TrainingProgram** (macro plan JSON, goal, volume constraints)
  - **WeekPlan** (planned vs actual tracking, adaptation notes)
  - **PlannedWorkout** (slots séances, link to WorkoutPlan, Activity matching)

### RAG Pipeline
- **`src/rag/knowledge_base.py`** - KnowledgeBase interface (query with score_threshold)
- **`src/rag/vector_store.py`** - Qdrant vector store (COSINE, 1536 dims)
- **`src/rag/embeddings.py`** - OpenAI text-embedding-3-small
- **`src/rag/document_processor.py`** - PDF chunking (800 chars, 150 overlap)
- **`data/books/`** - 14 PDFs scientifiques (Training and Racing with Power Meter, Science of Cycling, etc.)

### Strava Integration
- **`src/strava/client.py`** - OAuth flow, activity fetching, token refresh
- **`src/strava/data_processor.py`** - Activity processing, stream fetching (rate limited 0.2s), zone calculation
- **`src/strava/metrics.py`** - TSS, CTL/ATL/TSB calculations (exponential weighted averages)

### Visualizations
- **`src/visualization/charts.py`** (460 lignes) - 7 Plotly charts:
  - PMC (CTL/ATL/TSB), Weekly TSS, Zone distribution, Power curve
  - **Program timeline** (phase horizontal bars)
  - **Planned vs Actual TSS** (overlay bars per week)
  - **CTL progression** (projected vs actual line chart)

### Pages Streamlit
1. **`pages/1_Dashboard.py`** - Métriques fitness, PMC chart, 7d summary
2. **`pages/2_Analytics.py`** - Strava sync, training load trends, zone heatmap
3. **`pages/3_Settings.py`** - FTP, weight, préférences, agent memory notes
4. **`pages/4_Generate_Workout.py`** (300 lignes) - Single workout generation, 8 presets, type inference, feedback form, .zwo download
5. **`pages/5_Workout_Library.py`** - Saved workouts, filters, re-generate similar
6. **`pages/6_Training_Program.py`** (700 lignes) - **NEW**
   - View A: Program creation form (goal, FTP target, date, volume)
   - View B: Program overview (timeline, TSS chart, CTL progression, progress metrics)
   - View C: Week detail (workout cards, generate .zwo per session, re-plan week)

### Configuration
- **`config.py`** - Pydantic settings (OpenAI, Qdrant, Strava, DB)
- **`.env`** - API keys (openai_api_key, strava_client_id/secret, qdrant_url)
- **`data/trainer_agent.db`** - SQLite database

### Key Design Patterns
1. **Dual Agent Architecture**: PlanAgent (strategist) + WorkoutAgent (tactician) via workout_bridge
2. **Type-Aware Feedback**: Feedback grouped by workout_type to avoid cross-contamination (Recovery "too hard" ≠ VO2max "too hard")
3. **Multi-Query Adaptive RAG**: 4 queries (user + 2 type-specific + 1 fitness-state) → 8 results × 800 chars (~6400 chars context)
4. **Lazy Workout Generation**: PlannedWorkouts créés avec contraintes only, .zwo généré on-demand (évite waste si re-planning)
5. **Deterministic + LLM Hybrid**: AdaptationEngine rules (TSB guards) + LLM creative coaching
6. **Session State Detachment**: Toujours extraire SQLAlchemy objects en dicts DANS le `with get_db()` block (évite DetachedInstanceError)

### Performance
- **RAG query**: ~1-2s (Qdrant local/cloud)
- **Single workout generation**: ~5-10s (LLM + RAG + XML generation)
- **Program creation**: ~30-60s (macro plan design + N week plans DB insertion)
- **Weekly re-planning**: ~10-15s (nodes 5-6 + adaptation calculations)

### Limitations Connues
- Activity matching (Strava → PlannedWorkout) pas encore implémenté (need fuzzy TSS/date matching)
- Program pause/resume UI pas encore ajouté (status en DB existe)
- Mid-program FTP update pas encore géré (need recalc zones + optional re-plan)
- Batch workout generation pour semaine entière existe (workout_bridge) mais pas exposé UI

---

**Nom de code**: Trainer Agent 🚴💨

**Tagline**: "Your AI coach, powered by science, personalized by data"

**Status**: Phase 4 complète, Phase 5 en cours (production readiness)
