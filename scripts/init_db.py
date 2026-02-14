"""
Initialize the SQLite database with all tables
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database.database import init_db


if __name__ == "__main__":
    print("Initializing Trainer Agent database...")
    print("-" * 50)

    try:
        init_db()
        print("-" * 50)
        print("✓ Database initialization complete!")
        print("  Location: data/trainer_agent.db")
    except Exception as e:
        print(f"✗ Error initializing database: {e}")
        sys.exit(1)
