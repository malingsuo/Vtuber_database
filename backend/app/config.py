from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PostgreSQL 就緒後，在 backend/.env 設定：
    # DATABASE_URL=postgresql+psycopg://vtuber:vtuber@localhost:5432/vtuber_db
    # 在那之前先用 SQLite 檔案，讓開發不被環境卡住
    database_url: str = "sqlite:///./dev.db"

    # JWT 簽章金鑰：本機用預設值即可，上雲端「必須」在 .env 換成隨機長字串
    secret_key: str = "dev-only-secret-change-me-in-production"
    token_expire_hours: int = 72

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
