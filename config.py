"""
Central configuration management for Trainer Agent
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Application
    environment: str = "development"
    debug: bool = True

    # OpenAI
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-small"

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection_name: str = "cycling_knowledge"

    # Strava
    strava_client_id: str
    strava_client_secret: str
    strava_redirect_uri: str = "http://localhost:8501/Analytics"

    # Database
    database_url: str = "sqlite:///data/trainer_agent.db"

    # Streamlit
    streamlit_server_port: int = 8501
    streamlit_server_address: str = "localhost"

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
