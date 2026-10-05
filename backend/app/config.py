from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUTS_DIR = BASE_DIR / "outputs"
VOICES_DIR = BASE_DIR / "voices"

for d in (DATA_DIR, UPLOADS_DIR, OUTPUTS_DIR, VOICES_DIR):
    d.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{DATA_DIR / 'studio.db'}"

    jwt_secret: str = "change-me-in-.env"
    jwt_algorithm: str = "HS256"
    jwt_expires_days: int = 30

    studio_telegram_bot_token: str = ""
    studio_telegram_admin_ids: str = ""
    studio_telegram_signup: bool = True
    studio_admin_password: str = ""

    gemini_api_key: str = ""
    elevenlabs_api_key: str = ""
    voxcpm_url: str = ""

    domain: str = ""
    public_url: str = ""

    @property
    def telegram_admin_ids(self) -> set[str]:
        return {x.strip() for x in self.studio_telegram_admin_ids.split(",") if x.strip()}


settings = Settings()
