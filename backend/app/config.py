from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "mysql+asyncmy://tarot:tarot123@localhost:3306/tarot_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # DeepSeek API (OpenAI-compatible)
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    AI_MAX_TOKENS: int = 2048

    # WeChat
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""
    WECHAT_MCH_ID: str = ""
    WECHAT_API_KEY_V3: str = ""
    WECHAT_PLATFORM_CERT_SERIAL: str = ""
    WECHAT_PLATFORM_CERT: str = ""

    # Auth
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days

    # Limits
    FREE_DAILY_READINGS: int = 1
    FREE_CHAT_MESSAGES: int = 3

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
