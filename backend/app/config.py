from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "mysql+asyncmy://tarot:tarot123@localhost:3306/tarot_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # DeepSeek API (OpenAI-compatible)
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MODEL: str = "deepseek-v4-pro"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    AI_MAX_TOKENS: int = 4096

    # WeChat
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""
    WECHAT_MCH_ID: str = ""
    WECHAT_API_KEY_V3: str = ""
    WECHAT_PRIVATE_KEY_PATH: str = ""
    WECHAT_MCH_CERT_SERIAL: str = ""
    WECHAT_PLATFORM_CERT_SERIAL: str = ""  # REQUIRED for production. Get from WeChat Pay dashboard.
    WECHAT_PLATFORM_CERT: str = ""

    # Auth — JWT_SECRET is required; no default. Set via .env or environment variable.
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 30  # 30 days

    # Super admin — these user IDs bypass all free-tier limits.
    # Configured via .env as comma-separated UUIDs, e.g.
    #   SUPER_ADMIN_IDS=15eda012-5ad2-4211-ad06-072d194f617d,<other-id>
    # Kept as a raw string because pydantic-settings list[] fields demand JSON
    # env values; the method below splits the comma-separated form.
    SUPER_ADMIN_IDS: str = ""

    # Sentry
    SENTRY_DSN: str = ""

    # Dev login toggle — production must be false; backend guarded by 404
    ENABLE_DEV_LOGIN: bool = False

    # Shared secret required by the X-Dev-Key header on /auth/dev-login.
    # Leave empty to keep dev-login locked down (401) even in dev env.
    DEV_LOGIN_KEY: str = ""

    # Limits
    FREE_DAILY_READINGS: int = 5
    FREE_CHAT_MESSAGES: int = 3
    # Non-member AI extras (per day)
    FREE_REINTERPRETS_DAILY: int = 3    # POST /readings/{id}/reinterpret
    FREE_DIARY_AI_DAILY: int = 5        # diary reflection-prompt + review combined

    # Community content safety — WeChat msgSecCheck v2
    WECHAT_MSG_CHECK_ENABLED: bool = True

    # WeChat subscription-message template IDs (P0-4).
    # Fill with the REAL approved template IDs to enable push; empty = the
    # push service is disabled (subscribe returns 400 "推送服务未开通", and
    # send_subscribe_message logs "模板未配置" instead of calling WeChat).
    WX_TEMPLATE_DAILY_CARD: str = ""
    WX_TEMPLATE_MEMBER_EXPIRE: str = ""
    WX_TEMPLATE_ANNUAL_REPORT: str = ""

    # 虚拟支付 (xpay) + 小程序消息推送（回归修复：.env 已配置但这些字段缺失，
    # 在 pydantic-settings extra='forbid' 下导致整个后端无法启动/测试无法收集）
    WX_XPAY_OFFER_ID: str = ""
    WX_XPAY_APPKEY_SANDBOX: str = ""
    WX_XPAY_APPKEY_PROD: str = ""
    PAY_CHANNEL: str = "jsapi"  # xpay(虚拟支付) / jsapi(旧微信支付)
    WX_XPAY_ENV: int = 0        # 0=正式 1=沙箱
    XPAY_PRODUCT_MAP: str = "{}"
    WX_MSG_TOKEN: str = ""
    WX_MSG_ENCODING_AES_KEY: str = ""
    WX_MSG_ENCRYPT_MODE: str = "plain"  # plain / compatible / safe

    # Rate limiting
    RATE_LIMIT_MAX_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    model_config = SettingsConfigDict(env_file=".env")

    def super_admin_ids(self) -> list[str]:
        """Parse the comma-separated SUPER_ADMIN_IDS into a list of user ids."""
        return [
            part.strip()
            for part in (self.SUPER_ADMIN_IDS or "").split(",")
            if part.strip()
        ]


settings = Settings()
