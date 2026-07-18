from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # PostgreSQL 就緒後，在 backend/.env 設定：
    # DATABASE_URL=postgresql+psycopg://vtuber:vtuber@localhost:5432/vtuber_db
    # 在那之前先用 SQLite 檔案，讓開發不被環境卡住
    database_url: str = "sqlite:///./dev.db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
