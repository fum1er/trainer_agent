# Trainer Agent 🚴

Your AI-powered cycling training partner, powered by science and personalized by data.

## Features (Phase 1)

- 🔗 **Strava Integration**: OAuth authentication and activity sync
- 📊 **Training Metrics**: TSS, CTL, ATL, TSB calculations
- 📚 **Knowledge Base**: RAG pipeline with cycling training books
- ⚙️ **User Profiles**: FTP, zones, preferences management
- 🎨 **Streamlit UI**: Clean, intuitive interface

## Setup

### Prerequisites

- Python 3.10+
- Conda (Anaconda or Miniconda)
- Docker (for Qdrant vector database)
- Strava Developer Account
- OpenAI API Key

### Installation

1. **Clone repository**:
```bash
git clone <repo-url>
cd trainer_agent
```

2. **Create conda environment**:
```bash
conda env create -f environment.yml
conda activate trainer_agent
```

3. **Setup environment variables**:
```bash
cp .env.example .env
# Edit .env with your API keys
```

Required keys:
- `OPENAI_API_KEY`: Get from https://platform.openai.com/api-keys
- `STRAVA_CLIENT_ID` & `STRAVA_CLIENT_SECRET`: Get from https://www.strava.com/settings/api

4. **Start Qdrant (vector database)**:
```bash
docker run -d -p 6333:6333 qdrant/qdrant
```

5. **Initialize database**:
```bash
python scripts/init_db.py
```

6. **Ingest training books** (optional, requires PDFs in `data/books/`):
```bash
# Place your cycling training book PDFs in data/books/
python scripts/ingest_books.py
```

Recommended books:
- Training and Racing with a Power Meter (Hunter Allen, Andrew Coggan)
- The Cyclist's Training Bible (Joe Friel)

7. **Run Streamlit app**:
```bash
streamlit run app.py
```

## Strava Setup

1. Go to https://www.strava.com/settings/api
2. Create an application:
   - **Application Name**: Trainer Agent
   - **Category**: Training
   - **Authorization Callback Domain**: `localhost`
3. Copy **Client ID** and **Client Secret** to `.env`

## Project Structure

```
trainer_agent/
├── app.py                 # Main Streamlit app
├── config.py              # Configuration management
├── environment.yml        # Conda environment
├── src/                   # Source code
│   ├── database/          # SQLAlchemy models & DB connection
│   ├── rag/              # RAG pipeline (embeddings, vector store)
│   ├── strava/           # Strava integration (OAuth, metrics)
│   └── models/           # Domain models (Pydantic)
├── streamlit/            # Streamlit UI
│   └── pages/            # Multi-page app (Dashboard, Analytics, Settings)
├── scripts/              # Utility scripts
│   ├── init_db.py        # Initialize database
│   └── ingest_books.py   # Ingest training books into RAG
├── tests/                # Unit tests
└── data/                 # Data directory (gitignored)
    ├── books/            # Training book PDFs
    └── trainer_agent.db        # SQLite database
```

## Usage

### 1. Connect Strava

1. Go to **Analytics** page
2. Click "Connect Strava"
3. Authorize in browser
4. Copy the `code` parameter from the redirect URL
5. Paste into the input field

### 2. Set Your FTP

1. Go to **Settings** page
2. Enter your FTP (Functional Threshold Power) in watts
3. Optionally set weight and preferences
4. Click "Save Settings"

### 3. Sync Activities

1. Return to **Analytics** page
2. Click "Sync Last 6 Months"
3. Wait for activities to be fetched and processed
4. View your CTL, ATL, TSB metrics

### 4. Explore Dashboard

1. Go to **Dashboard** page
2. View your training metrics overview
3. (Phase 2+: View charts and trends)

### 5. Test Knowledge Base

1. Go to **Settings** page
2. Scroll to "Test Knowledge Base"
3. Ask a training question (e.g., "What is FTP?")
4. View relevant passages from training books

## Running Tests

```bash
pytest tests/ -v
```

Specific test files:
```bash
pytest tests/test_calculations.py -v
pytest tests/test_database.py -v
pytest tests/test_rag.py -v
```

## Development

### Code Style

```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy src/
```

### Database Management

**Initialize database**:
```bash
python scripts/init_db.py
```

**Inspect database** (using SQLite browser or CLI):
```bash
sqlite3 data/trainer_agent.db
.schema
.tables
```

### RAG Pipeline

**Test Qdrant connection**:
```bash
# Check if Qdrant is running
curl http://localhost:6333/collections
```

**Reingest books**:
```bash
python scripts/ingest_books.py
```

## Configuration

All configuration is managed via environment variables in `.env`:

- **OPENAI_API_KEY**: OpenAI API for embeddings
- **QDRANT_URL**: Qdrant vector database URL (default: `http://localhost:6333`)
- **STRAVA_CLIENT_ID**: Strava OAuth client ID
- **STRAVA_CLIENT_SECRET**: Strava OAuth client secret
- **DATABASE_URL**: SQLite database path (default: `sqlite:///data/trainer_agent.db`)

## Troubleshooting

### Qdrant Connection Failed

**Problem**: Cannot connect to Qdrant.

**Solution**:
```bash
# Check if Docker is running
docker ps

# Check if Qdrant container is running
docker ps | grep qdrant

# Restart Qdrant
docker restart <container-id>

# Or start fresh
docker run -d -p 6333:6333 qdrant/qdrant
```

### Strava OAuth Not Working

**Problem**: Authorization code invalid or expired.

**Solution**:
- Make sure callback domain in Strava app settings is `localhost`
- Get a fresh authorization code (they expire quickly)
- Check that CLIENT_ID and CLIENT_SECRET in `.env` are correct

### Database Locked Error

**Problem**: SQLite database is locked.

**Solution**:
```bash
# Close all Streamlit sessions
# Re-initialize database
python scripts/init_db.py
```

### OpenAI API Rate Limit

**Problem**: Hitting OpenAI rate limits during book ingestion.

**Solution**:
- Use smaller batch sizes in `ingest_books.py`
- Wait a few minutes and retry
- Consider using Qdrant Cloud free tier with pre-computed embeddings

## Roadmap

- ✅ **Phase 1: Foundation** (Current)
  - Database, RAG, Strava integration, basic UI

- ⏳ **Phase 2: Core Agent** (Next)
  - LangGraph workout generation agent
  - .zwo file structured output
  - Single workout generation

- ⏳ **Phase 3: Intelligence**
  - Memory and user adaptation
  - Advanced analytics charts
  - Workout library

- ⏳ **Phase 4: Advanced**
  - Long-term mesocycle planning
  - Multi-week programs
  - Advanced RAG queries

- ⏳ **Phase 5: Production**
  - End-to-end testing
  - Error handling
  - Deployment (Streamlit Cloud)

## Architecture

### Training Metrics

**Normalized Power (NP)**: Fourth root of average of fourth power of 30-second rolling average

**Intensity Factor (IF)**: NP / FTP

**TSS** (Training Stress Score): (duration_seconds × NP × IF) / (FTP × 3600) × 100

**CTL** (Chronic Training Load): Exponentially weighted 42-day average of daily TSS (fitness)

**ATL** (Acute Training Load): Exponentially weighted 7-day average of daily TSS (fatigue)

**TSB** (Training Stress Balance): CTL - ATL (form)

### Power Zones

- **Z1**: <55% FTP (Recovery)
- **Z2**: 56-75% FTP (Endurance)
- **Z3**: 76-90% FTP (Tempo)
- **Z4**: 91-105% FTP (Threshold)
- **Z5**: 106-120% FTP (VO2max)
- **Z6**: 121-150% FTP (Anaerobic)
- **Z7**: >150% FTP (Neuromuscular)

## Contributing

This is currently a personal project. Contributions welcome after Phase 2 completion.

## License

MIT

## Credits

**Nom de code**: Trainer Agent 🚴💨

**Tagline**: "Your AI coach, powered by science, personalized by data"

Built with:
- LangChain for RAG
- Qdrant for vector storage
- Streamlit for UI
- Strava API for training data
- OpenAI for embeddings
