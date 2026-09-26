"""Service settings. Everything comes from the environment; secrets never leave this process."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

    # ---- Meta WhatsApp Cloud API ----
    whatsapp_access_token: SecretStr = SecretStr('')
    whatsapp_phone_number_id: str = ''
    whatsapp_business_account_id: str = ''
    whatsapp_verify_token: SecretStr = SecretStr('')
    # App secret signs every webhook POST (X-Hub-Signature-256). Strongly recommended.
    whatsapp_app_secret: SecretStr = SecretStr('')
    whatsapp_api_version: str = 'v23.0'
    whatsapp_graph_url: str = 'https://graph.facebook.com'

    # ---- Biz GPT (Open WebUI) ----
    openwebui_base_url: str = 'http://bizgpt-webui:8080'
    openwebui_api_key: SecretStr = SecretStr('')
    # Workspace model that answers WhatsApp customers (Workspace → Models id).
    whatsapp_agent_model: str = 'bizgpt-whatsapp'
    # Also save each WhatsApp conversation as a Biz GPT chat, so staff can read it.
    openwebui_mirror_chats: bool = True
    openwebui_timeout_seconds: float = 90.0

    # ---- This service ----
    database_url: str = 'postgresql+asyncpg://whatsapp:whatsapp@whatsapp-db:5432/whatsapp'
    # Bearer key for the internal API (Biz GPT tool + Integrations page). Not for Meta.
    whatsapp_service_api_key: SecretStr = SecretStr('')
    auto_reply_enabled: bool = True
    history_messages: int = Field(default=20, ge=1, le=100)
    conversation_timeout_hours: float = 24.0
    # Inbound AI replies per contact per minute; extra messages are stored but not answered.
    rate_limit_per_minute: int = 10
    mark_as_read: bool = True
    unsupported_reply: str = 'Sorry, I can only read text messages, images and documents right now. Please type your question.'
    fallback_reply: str = 'Sorry, I could not answer that just now. Please try again in a moment.'
    http_retries: int = 3
    meta_timeout_seconds: float = 15.0
    log_level: str = 'INFO'

    def secret_values(self) -> list[str]:
        return [
            s.get_secret_value()
            for s in (
                self.whatsapp_access_token,
                self.whatsapp_verify_token,
                self.whatsapp_app_secret,
                self.openwebui_api_key,
                self.whatsapp_service_api_key,
            )
            if s.get_secret_value()
        ]

    @property
    def meta_configured(self) -> bool:
        return bool(self.whatsapp_access_token.get_secret_value() and self.whatsapp_phone_number_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
