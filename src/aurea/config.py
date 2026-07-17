import os
from pathlib import Path
from typing import List, Optional
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve root directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

class VehicleFilter(BaseModel):
    makes: List[str] = Field(default_factory=list)
    models: List[str] = Field(default_factory=list)
    min_year: Optional[int] = None
    max_mileage_km: Optional[int] = None
    fuels: List[str] = Field(default_factory=list)
    preferred_fuels: List[str] = Field(default_factory=list)
    transmissions: List[str] = Field(default_factory=list)
    max_age_days: Optional[int] = 30

class PriceFilter(BaseModel):
    max_price_eur: Optional[float] = None
    minimum_adjusted_discount_percent: float = 20.0
    minimum_adjusted_saving_eur: float = 3000.0

class LocationFilter(BaseModel):
    country: str = "ES"
    radius_km: Optional[int] = None
    places: List[str] = Field(default_factory=list)

class AlertingFilter(BaseModel):
    required_rating: int = 10
    maximum_alerts_per_run: int = 2

class ExclusionsFilter(BaseModel):
    damaged: bool = True
    mechanical_failure: bool = True
    financing_price: bool = True
    no_itv: bool = True
    professional_only: bool = True
    auction: bool = True
    incomplete_documentation: bool = True

class SearchConfig(BaseModel):
    id: str
    enabled: bool = True
    vehicle: VehicleFilter = Field(default_factory=VehicleFilter)
    price: PriceFilter = Field(default_factory=PriceFilter)
    location: LocationFilter = Field(default_factory=LocationFilter)
    alerting: AlertingFilter = Field(default_factory=AlertingFilter)
    exclusions: ExclusionsFilter = Field(default_factory=ExclusionsFilter)

class DatabaseSettings(BaseModel):
    url: str = "sqlite:///data/aurea.db"

class TelegramSettings(BaseModel):
    bot_token: str = ""
    chat_id: str = ""

class ScrapingSettings(BaseModel):
    timeout_seconds: int = 15
    use_fixtures_fallback: bool = True
    user_agent: str = "Mozilla/5.0"

class AnalysisSettings(BaseModel):
    market_confidence_threshold: float = 0.90
    vehicle_confidence_threshold: float = 0.88
    minimum_comparables: int = 8
    min_comparables_rare_vehicle: int = 5
    rare_vehicle_confidence_threshold: float = 0.90

class Settings(BaseSettings):
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    scraping: ScrapingSettings = Field(default_factory=ScrapingSettings)
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore"
    )

def load_settings() -> Settings:
    # 1. Load defaults
    settings_dict = {}
    
    # 2. Try loading settings.yaml if it exists
    settings_path = PROJECT_ROOT / "config" / "settings.yaml"
    if not settings_path.exists():
        settings_path = PROJECT_ROOT / "config" / "settings.example.yaml"
        
    if settings_path.exists():
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
                if loaded:
                    settings_dict.update(loaded)
        except Exception:
            pass

    # Convert telegram fields specifically if present in ENV
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat = os.environ.get("TELEGRAM_CHAT_ID")
    
    if "telegram" not in settings_dict:
        settings_dict["telegram"] = {}
    if telegram_token:
        settings_dict["telegram"]["bot_token"] = telegram_token
    if telegram_chat:
        settings_dict["telegram"]["chat_id"] = telegram_chat

    # Convert database url if present in ENV
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        if "database" not in settings_dict:
            settings_dict["database"] = {}
        settings_dict["database"]["url"] = db_url

    # Standardize sqlite path to absolute if it is sqlite:///data/aurea.db
    # This is critical so running from different folders doesn't create multiple databases
    if "database" in settings_dict and "url" in settings_dict["database"]:
        url = settings_dict["database"]["url"]
        if url.startswith("sqlite:///data/"):
            db_dir = PROJECT_ROOT / "data"
            db_dir.mkdir(exist_ok=True)
            db_path = db_dir / url.split("sqlite:///data/")[-1]
            settings_dict["database"]["url"] = f"sqlite:///{db_path.resolve().as_posix()}"

    return Settings(**settings_dict)

def load_searches() -> List[SearchConfig]:
    searches_path = PROJECT_ROOT / "config" / "searches.yaml"
    if not searches_path.exists():
        searches_path = PROJECT_ROOT / "config" / "searches.example.yaml"
        
    if not searches_path.exists():
        return []

    try:
        with open(searches_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if not data or "searches" not in data:
                return []
            return [SearchConfig(**s) for s in data["searches"]]
    except Exception:
        return []
