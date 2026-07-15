from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "SEACE Radar Gov Peru API")
    environment: str = os.getenv("ENVIRONMENT", "local")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./data/seace_radar.db")
    secret_key: str = os.getenv("SECRET_KEY", "change-me-before-production")
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "720"))
    password_reset_minutes: int = int(os.getenv("PASSWORD_RESET_MINUTES", "30"))
    frontend_url: str = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")
    auto_create_tables: bool = os.getenv("AUTO_CREATE_TABLES", "false").lower() == "true"
    enable_menor8_module: bool = os.getenv("ENABLE_MENOR8_MODULE", "false").lower() == "true"
    enable_chile_grandes_compras: bool = os.getenv("ENABLE_CHILE_GRANDES_COMPRAS", "false").lower() == "true"
    enable_scheduler: bool = os.getenv("ENABLE_SCHEDULER", "false").lower() == "true"
    scheduler_interval_minutes: int = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "15"))
    auto_send_alerts: bool = os.getenv("AUTO_SEND_ALERTS", "false").lower() == "true"
    alert_sender_interval_minutes: int = int(os.getenv("ALERT_SENDER_INTERVAL_MINUTES", "10"))
    alert_batch_size: int = int(os.getenv("ALERT_BATCH_SIZE", "50"))
    alert_max_attempts: int = int(os.getenv("ALERT_MAX_ATTEMPTS", "5"))
    alert_retry_base_minutes: int = int(os.getenv("ALERT_RETRY_BASE_MINUTES", "5"))
    email_provider: str = os.getenv("EMAIL_PROVIDER", "smtp").lower()
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from: str = os.getenv("SMTP_FROM", "")
    azure_communication_connection_string: str = os.getenv("AZURE_COMMUNICATION_CONNECTION_STRING", "")
    azure_email_sender: str = os.getenv("AZURE_EMAIL_SENDER", "")
    whatsapp_enabled: bool = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"
    whatsapp_provider: str = os.getenv("WHATSAPP_PROVIDER", "")
    whatsapp_token: str = os.getenv("WHATSAPP_TOKEN", "")
    whatsapp_api_url: str = os.getenv("WHATSAPP_API_URL", "")
    whatsapp_from: str = os.getenv("WHATSAPP_FROM", "")
    whatsapp_channel_id: str = os.getenv("WHATSAPP_CHANNEL_ID", "")
    whatsapp_template_name: str = os.getenv("WHATSAPP_TEMPLATE_NAME", "govradar_alert")
    whatsapp_template_language: str = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "es")
    cors_origins: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8501,http://127.0.0.1:8501",
    )


settings = Settings()
