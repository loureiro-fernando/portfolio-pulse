"""Pytest fixtures + early env setup for skill evals.

Mirrors tests/conftest.py: sets dummy env vars before any `from app.*` import
so that pydantic-settings doesn't blow up when no .env is present.
"""

import os

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-dummy-eval-key-do-not-use")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://pulse:pulse_dev@localhost:5432/portfolio_pulse"
)
os.environ.setdefault("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
os.environ.setdefault("JWT_SECRET", "dummy-jwt-secret-for-tests-32-chars-min")
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-dummy-eval-token")
os.environ.setdefault("SLACK_PORTFOLIO_CHANNEL", "portfolio-pulse")
