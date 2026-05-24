"""Pytest fixtures + early env setup.

`app.config.Settings` instantiates at import time and requires the .env to be
present. In CI there is no .env, so this conftest sets minimal dummy values
*before* any `from app.*` import happens (pytest loads conftest before tests).
"""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-dummy-ci-key-do-not-use")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://pulse:pulse_dev@localhost:5432/portfolio_pulse"
)
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
os.environ.setdefault("JWT_SECRET", "dummy-jwt-secret-for-tests-32-chars-min")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-dummy-ci-token")
os.environ.setdefault("SLACK_PORTFOLIO_CHANNEL", "portfolio-pulse")
