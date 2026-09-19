import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "Instagram Reel Fact-Checker"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Paths
    BASE_DIR: Path = BASE_DIR
    DATA_DIR: Path = BASE_DIR / "data"
    RAW_DIR: Path = BASE_DIR / "data" / "raw"
    AUDIO_DIR: Path = BASE_DIR / "data" / "audio"
    FRAMES_DIR: Path = BASE_DIR / "data" / "frames"
    CACHE_DIR: Path = BASE_DIR / "data" / "cache"
    CHROMA_DIR: Path = BASE_DIR / "data" / "cache" / "chroma"
    DATABASE_URL: str = f"sqlite+aiosqlite:///{BASE_DIR}/data/database.sqlite"

    # LLM Settings
    LLM_PROVIDER: str = "ollama"  # "ollama", "gemini", "openai", "lmstudio"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2:3b"
    LMSTUDIO_BASE_URL: str = "http://localhost:1234/v1"
    LMSTUDIO_MODEL: str = "local-model"
    
    # Cloud LLM keys (optional fallbacks)
    GEMINI_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Search & Verification
    SEARCH_PROVIDER: str = "duckduckgo"  # "duckduckgo", "tavily"
    TAVILY_API_KEY: str = ""
    MAX_SEARCH_RESULTS_PER_CLAIM: int = 5
    MAX_EVIDENCE_PER_CLAIM: int = 3
    
    # Ingestion & Perception Models
    WHISPER_MODEL: str = "base"  # "tiny", "base", "small", "medium"
    WHISPER_DEVICE: str = "cuda"  # "cuda" or "cpu"
    WHISPER_COMPUTE_TYPE: str = "float16"  # "float16", "int8", "float32"
    OCR_USE_GPU: bool = True
    FRAME_SAMPLE_INTERVAL: float = 1.5  # Sample a frame every 1.5s
    
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def init_directories(self):
        for path in [self.DATA_DIR, self.RAW_DIR, self.AUDIO_DIR, self.FRAMES_DIR, self.CACHE_DIR, self.CHROMA_DIR]:
            path.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.init_directories()
