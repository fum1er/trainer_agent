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

### 3. Agent Architecture (LangGraph)

```python
# Flow simplifié
State: {
    user_profile,
    training_history,
    constraints,  # durée dispo, objectif, deadline
    rag_context,
    workout_draft,
    structured_output
}

Nodes:
1. analyze_rider → profil actuel (CTL, TSB, forces/faiblesses)
2. retrieve_theory → RAG query selon objectif
3. plan_mesocycle → structure macro si programme long
4. generate_workout → création séance(s)
5. validate_load → check TSS cohérence avec charge actuelle
6. format_zwo → structured output .zwo
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

### Phase 4: Advanced (Week 7-8)
- Long-term planning (mesocycles)
- Multi-week program generation
- Advanced RAG queries (contexte spécifique)
- Polish UI/UX

### Phase 5: Production (Week 9-10)
- Testing end-to-end
- Error handling
- Documentation
- Deploy (Streamlit Cloud ou self-hosted)

---

**Nom de code**: Trainer Agent 🚴💨

**Tagline**: "Your AI coach, powered by science, personalized by data"
