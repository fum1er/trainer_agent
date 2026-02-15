# Phase 4: Training Programs - Documentation Technique

## Vue d'Ensemble

Phase 4 ajoute la **planification long terme** (4-24 semaines) avec périodisation scientifique, adaptations hebdomadaires automatiques, et intégration complète avec le système de génération de séances existant.

## Architecture Dual-Agent

### 1. PlanAgent (Stratégiste)
**Rôle**: Créer et adapter les plans macro de périodisation

**LangGraph Flow (6 nodes)**:
```
parse_goal → analyze_current_fitness → retrieve_periodization_theory
→ design_macro_plan → plan_current_week → distribute_workouts
```

**Inputs**:
- Goal description (texte libre ou structuré)
- Target FTP / race date
- Volume disponible (heures/semaine, sessions/semaine)
- Historique Strava (90 derniers jours)
- Profil actuel (FTP, CTL, ATL, TSB)

**Outputs**:
- Macro plan JSON (phases, TSS targets, zone focus)
- Week plans (target TSS, zone focus, instructions coaching)
- Planned workouts (type, TSS, durée, contraintes)

**Entry Points**:
```python
# Création programme complet
result = plan_agent.create_program(
    user_input="Objectif 300W FTP dans 4 mois",
    user_profile={"ftp": 265, "ctl": 72, "tsb": -5},
    training_history=[...],
    feedback_history=[...]
)

# Re-planification hebdomadaire
result = plan_agent.plan_week(
    program=training_program,  # DB object
    week_number=3,
    user_profile={...},
    recent_weeks=[week1, week2]  # DB objects
)
```

### 2. WorkoutAgent (Tacticien)
**Rôle**: Générer séances individuelles avec créativité maximale

**Inchangé** depuis Phase 3, mais maintenant utilisé via le **workout_bridge** pour générer les séances d'un programme.

**Integration**:
```python
from src.agent.workout_bridge import generate_planned_workout

result = generate_planned_workout(
    planned_workout=planned_workout_db,  # PlannedWorkout object
    user_profile={...},
    training_history=[...],
    feedback_history=[...]
)
# Returns: {workout_xml, reasoning, structure}
```

### 3. AdaptationEngine (Moteur Adaptatif)
**Rôle**: Logique déterministe pour ajuster les plans selon fatigue/compliance

**Méthodes clés**:
```python
engine = AdaptationEngine()

# Analyser compliance semaine passée
compliance = engine.analyze_compliance(week_plan)
# → {tss_compliance: 0.85, sessions_compliance: 1.0, ...}

# Calculer ajustements pour semaine prochaine
adjustments = engine.calculate_adjustments(
    program=program,
    current_week_number=4,
    current_profile={"tsb": -12, "ctl": 78},
    recent_weeks=[week1, week2, week3]
)
# → {tss_multiplier: 0.85, reasons: ["TSB below -10, reducing load"]}

# Détecter risque surmenage
risk = engine.detect_overtraining_risk(profile, recent_weeks)
# → {risk_level: "medium", warnings: ["TSB below -15"]}
```

**Règles d'adaptation**:
| Condition | Action | Multiplier TSS |
|-----------|--------|----------------|
| TSB < -20 | Force recovery week | 0.5× |
| TSB < -10 | Reduce load | 0.85× |
| Compliance < 70% (2 weeks) | Lower targets | 0.80× |
| CTL ramp > 7 TSS/day | Back off | 0.90× |
| TSB > 15 | Increase load | 1.10× |

## Modèles Base de Données

### TrainingProgram
```python
TrainingProgram:
    - id, user_id, name, goal_type, goal_description
    - target_ftp, target_date, start_date
    - hours_per_week, sessions_per_week
    - macro_plan_json (TEXT)  # Full JSON blob
    - initial_ftp, initial_ctl
    - status (active/completed/paused/cancelled)
    - week_plans (relationship)
```

**macro_plan_json structure**:
```json
{
  "total_weeks": 16,
  "phases": [
    {
      "name": "Base",
      "weeks": [1, 6],
      "weekly_tss_range": [350, 450],
      "zone_focus": ["Endurance", "Tempo", "Sweet Spot"],
      "zone_distribution": {"Z2": 0.60, "Z3": 0.20, ...},
      "intensity_profile": "high_volume_low_intensity"
    },
    // Build, Peak, Taper phases...
  ],
  "progression_rules": {
    "max_tss_increase_pct": 10,
    "recovery_week_frequency": 4,
    "max_ctl_ramp_rate": 7
  },
  "week_targets": [
    {"week": 1, "tss": 350, "phase": "Base", "is_recovery": false},
    {"week": 4, "tss": 240, "phase": "Base", "is_recovery": true},
    // ... all weeks
  ]
}
```

### WeekPlan
```python
WeekPlan:
    - id, program_id, week_number, phase

    # Planned (set by PlanAgent)
    - target_tss, target_hours, target_sessions
    - zone_focus (CSV string)
    - week_instructions (coaching text)

    # Actual (filled from Strava after completion)
    - actual_tss, actual_hours, actual_sessions
    - actual_ctl, actual_atl, actual_tsb

    # Adaptation
    - adaptation_notes (e.g., "Reduced TSS by 15% due to fatigue")
    - status (upcoming/current/completed/skipped)
    - start_date, end_date

    - planned_workouts (relationship)
```

### PlannedWorkout
```python
PlannedWorkout:
    - id, week_plan_id, day_index (1-7)
    - workout_type (Sweet Spot, VO2max, etc.)
    - target_tss, target_duration (minutes)
    - instructions (text to pass to WorkoutAgent)

    # Links
    - workout_plan_id (FK to WorkoutPlan, NULL until generated)
    - activity_id (FK to Activity, NULL until Strava match)

    - status (planned/generated/completed/skipped)
```

## Flow Utilisateur Complet

### 1. Création Programme

**UI**: Page Training Program > Create New Program

```
User Input:
├─ Goal: "Increase FTP to 300W for summer racing"
├─ Target Date: 2026-06-15 (16 weeks)
├─ Volume: 10h/week, 5 sessions/week
└─ Current: FTP 265W, CTL 72

↓ (30-60s)

PlanAgent.create_program():
├─ parse_goal → validate timeline (16 weeks, +35W = realistic)
├─ analyze_current_fitness → 90d trends, zone distribution
├─ retrieve_periodization_theory → RAG queries (6 passages)
├─ design_macro_plan → LLM generates JSON
│   ├─ Base: weeks 1-8 (350-450 TSS)
│   ├─ Build: weeks 9-13 (400-520 TSS)
│   ├─ Peak: weeks 14-15 (480 TSS)
│   └─ Taper: week 16 (250 TSS)
├─ plan_current_week (week 1) → target_tss=350, zone_focus="Endurance,Tempo"
└─ distribute_workouts → 5 slots (2 hard, 2 moderate, 1 easy)

↓

Database:
├─ TrainingProgram created (macro_plan_json saved)
├─ 16 WeekPlan rows created (status="upcoming" sauf week 1 = "current")
└─ 0 PlannedWorkout rows (lazy generation)

↓

UI: Redirect to Program Overview
```

### 2. Visualisation Overview

**UI**: Program Overview page

```
Display:
├─ Progress: "Week 1/16 completed"
├─ FTP: "265W → 300W" (target)
├─ Timeline: [Base────────Build──Peak─T]
├─ TSS Chart: planned (outline) vs actual (filled) bars
└─ CTL Chart: projected (dash) vs actual (solid) line

User clicks: "View Current Week" → Week 1 Detail
```

### 3. Planification Semaine (Lazy)

**UI**: Week Detail page, week 1

```
Week 1 not yet planned → Button "Plan Workouts for This Week"

↓

PlanAgent.plan_week(week_number=1):
├─ Load macro_plan from program
├─ Check recent_weeks (empty, first week)
├─ AdaptationEngine.calculate_adjustments → no adjustments (TSB OK)
├─ plan_current_week → target_tss=350, instructions
└─ distribute_workouts → 5 PlannedWorkout specs

↓

Database:
└─ 5 PlannedWorkout rows created:
    ├─ Workout 1: Endurance, 80 TSS, 120min (status=planned)
    ├─ Workout 2: Sweet Spot, 75 TSS, 90min (status=planned)
    ├─ Workout 3: Tempo, 60 TSS, 90min (status=planned)
    ├─ Workout 4: Recovery, 30 TSS, 60min (status=planned)
    └─ Workout 5: Endurance, 75 TSS, 120min (status=planned)

↓

UI: Display 5 workout cards with [Generate .zwo] buttons
```

### 4. Génération Séance

**UI**: Week Detail, User clicks "Generate .zwo" on Workout 2

```
PlannedWorkout 2:
├─ workout_type: "Sweet Spot"
├─ target_tss: 75
├─ target_duration: 90min
└─ instructions: "Sweet Spot session for Base phase..."

↓

workout_bridge.generate_planned_workout():
├─ Build constrained input for WorkoutAgent:
│   "Sweet Spot session for Base phase.
│    Target TSS: 75, Duration: 90min, ..."
├─ WorkoutAgent.generate_workout() → (existing flow)
│   ├─ analyze_rider, retrieve_memory, retrieve_theory
│   ├─ plan_workout (creative intervals)
│   ├─ generate_structure
│   └─ format_zwo → .zwo XML
└─ validate_workout_constraints → check ±15% tolerance

↓

Database:
├─ WorkoutPlan created (name="Criss-Cross SS", zwo_xml, ...)
└─ PlannedWorkout.workout_plan_id linked, status="generated"

↓

UI: [Download .zwo] button appears
```

### 5. Adaptation Hebdomadaire

**Semaine 1 terminée → User syncs Strava**

```
Strava Sync:
└─ Activities fetched → TSS calculated → Week 1 actual_tss = 300 (target was 350)

Update Database:
├─ WeekPlan 1:
│   ├─ actual_tss = 300 (85% compliance)
│   ├─ actual_ctl = 74
│   ├─ actual_tsb = -8
│   └─ status = "completed"
└─ WeekPlan 2:
    └─ status = "current"
```

**User navigates to Week 2**

```
Week 2 not yet planned → Auto-trigger plan_week()

PlanAgent.plan_week(week_number=2):
├─ Load recent_weeks = [week1]
├─ AdaptationEngine.calculate_adjustments:
│   ├─ TSB = -8 (OK, no reduction needed)
│   ├─ Compliance week1 = 0.85 (acceptable)
│   └─ adjustments = {tss_multiplier: 1.0, reasons: []}
├─ plan_current_week → target_tss=375 (from macro plan)
└─ distribute_workouts → 5 PlannedWorkout specs

↓

Database: 5 new PlannedWorkout rows for week 2

UI: Display workouts, [Generate .zwo] buttons
```

**Si TSB était critique (-20)**:

```
AdaptationEngine.calculate_adjustments:
├─ TSB = -20
├─ adjustments = {
│     tss_multiplier: 0.5,
│     force_recovery: true,
│     reasons: ["TSB critically low, forcing recovery week"]
│   }
└─ plan_current_week → target_tss=375 × 0.5 = 187.5

↓

WeekPlan 2:
├─ target_tss = 187.5 (adapté!)
└─ adaptation_notes = "Reduced TSS by 50% due to critical fatigue (TSB: -20)"
```

## Visualisations

### Program Timeline
```python
create_program_timeline(macro_plan_json)
```
Horizontal stacked bar chart:
- X-axis: weeks 1-16
- Bars: [Base (blue)][Build (orange)][Peak (red)][Taper (green)]
- Hover: phase name, week range, duration

### Planned vs Actual TSS
```python
create_planned_vs_actual_tss(week_plans)
```
Grouped bar chart per week:
- Planned TSS: outline bars (gray border)
- Actual TSS: filled bars (colored by phase)
- Overlay mode

### CTL Progression
```python
create_program_progress_chart(program, week_plans)
```
Line chart:
- Projected CTL: dashed blue line (calculated from macro plan)
- Actual CTL: solid green line (from Strava data)
- Shows fitness trajectory

## Testing

### Test Import
```bash
python scripts/test_phase4_imports.py
```
Vérifie que tous les modules s'importent correctement.

### Test End-to-End (Manuel)
1. **Créer programme**:
   - Page Training Program > Create New
   - Fill form, click "Create Plan"
   - Vérifier redirect vers Overview
   - Vérifier timeline chart s'affiche

2. **Voir week detail**:
   - Click "View Current Week"
   - Click "Plan Workouts for This Week"
   - Vérifier 5 workouts apparaissent

3. **Générer séance**:
   - Click "Generate .zwo" sur un workout
   - Vérifier génération réussit (~10s)
   - Click "Download .zwo"
   - Vérifier fichier XML valide

4. **Adapter semaine suivante**:
   - Modifier manually actual_tss de week 1 dans DB
   - Set TSB à -18
   - Navigate to week 2
   - Vérifier adaptation notes apparaît

## Limitations Connues

### 1. Activity Matching (TODO Phase 5)
- **Problème**: PlannedWorkout.activity_id non peuplé automatiquement
- **Workaround**: Matching manuel via TSS + date fuzzy logic
- **Solution**: Implement dans `src/strava/activity_matcher.py`

### 2. Program Pause/Resume (TODO Phase 5)
- **Problème**: Status "paused" existe mais pas d'UI pour trigger
- **Solution**: Ajouter bouton "Pause Program" dans Overview
- **Impact**: Besoin de décaler start_date des semaines futures

### 3. Mid-Program FTP Update (TODO Phase 5)
- **Problème**: Si FTP change (nouveau test), zones pas recalculées
- **Workaround**: Manually update user_profile.ftp
- **Solution**: Implement "Update FTP" flow avec optional re-plan

### 4. Batch Workout Generation (Exists but not exposed)
- **Fonction**: `batch_generate_week_workouts()` existe dans workout_bridge
- **UI**: Pas de bouton "Generate All Workouts for This Week"
- **Raison**: User peut vouloir regenerate individually si pas satisfait

## Performance Optimizations

### 1. Macro Plan Caching
```python
# Le macro_plan_json est stocké une fois en DB
# Pas de re-calcul à chaque week planning
macro_plan = json.loads(program.macro_plan_json)
```

### 2. Lazy Workout Generation
```python
# PlannedWorkouts créés sans .zwo
# Generate on-demand quand user click
# Évite waste si re-planning needed
```

### 3. Session State Detachment Fix
```python
# ALWAYS extract SQLAlchemy data inside with get_db():
with get_db() as db:
    program = db.query(TrainingProgram).first()
    program_data = {
        "id": program.id,
        "name": program.name,
        # ... tous les champs
    }
# Use program_data outside session
```

## API Reference

### PlanAgent
```python
class PlanAgent:
    def create_program(
        user_input: str,
        user_profile: dict,
        training_history: list,
        feedback_history: list
    ) -> dict:
        """Returns: {macro_plan, first_week_detail, reasoning, goal}"""

    def plan_week(
        program: TrainingProgram,
        week_number: int,
        user_profile: dict,
        recent_weeks: list[WeekPlan]
    ) -> dict:
        """Returns: {week_detail, reasoning}"""
```

### AdaptationEngine
```python
class AdaptationEngine:
    def analyze_compliance(week_plan: WeekPlan) -> dict
    def calculate_adjustments(program, week_number, profile, recent_weeks) -> dict
    def detect_overtraining_risk(profile, recent_weeks) -> dict
    def recommend_recovery_week(program, week_number) -> bool
    def adjust_week_distribution(target_tss, sessions, zone_focus, profile) -> list
```

### workout_bridge
```python
def generate_planned_workout(
    planned_workout: PlannedWorkout,
    user_profile: dict,
    training_history: list,
    feedback_history: list
) -> dict:
    """Returns: {workout_xml, reasoning, structure}"""

def validate_workout_constraints(
    generated_workout: dict,
    planned_workout: PlannedWorkout,
    tolerance: float = 0.15
) -> dict:
    """Returns: {is_valid, warnings, actual_vs_target}"""
```

## Troubleshooting

### Erreur: "TSS progression too aggressive"
- **Cause**: LLM generated macro plan with >10% TSS increase per week
- **Fix**: Add validation in `design_macro_plan` node to reject + retry

### Erreur: "DetachedInstanceError"
- **Cause**: Accessing SQLAlchemy object outside session
- **Fix**: Extract all data into dict INSIDE `with get_db()` block

### Erreur: "Week not found"
- **Cause**: WeekPlan rows not created during program creation
- **Fix**: Check program creation flow saves N WeekPlan rows

### Génération séance timeout
- **Cause**: WorkoutAgent LLM call took >2min
- **Fix**: Increase timeout or check OpenAI API status

---

**Prochaines étapes Phase 5**:
1. Activity matching automatique (Strava → PlannedWorkout)
2. Program pause/resume UI
3. Mid-program FTP update flow
4. Testing end-to-end complet (4-week mini program)
5. Error handling robustesse
6. Deploy production
