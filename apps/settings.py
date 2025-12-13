from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENV: str = "dev"
    BASE_URL: str = "http://localhost:8080"
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str

    OPENAI_API_KEY: str
    OPENAI_MODEL: str = "gpt-5"

    GOOGLE_OAUTH_CLIENT_ID: str | None = None
    GOOGLE_OAUTH_CLIENT_SECRET: str | None = None
    GOOGLE_OAUTH_REDIRECT_URI: str | None = None

    GMAIL_USER: str = "me"

    PUBSUB_VERIFICATION_TOKEN: str | None = None

    AUTO_CREATE_DRAFTS: bool = True
    AUTO_SEND_LOW_RISK: bool = False

settings = Settings()
