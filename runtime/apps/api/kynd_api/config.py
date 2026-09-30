"""Application configuration.

Every value that differs between developer machines, CI, and production lives
here and comes from the environment. Nothing secret has a usable default: a
missing credential key or session secret must fail loudly at startup rather
than silently fall back to a value an attacker could guess.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_prefix="KYND_",
    )

    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+psycopg://localhost/kynd_os_dev"

    # Where per-workspace runtime enforcement state lives. One SQLite file per
    # workspace — see docs/saas/SAAS_ARCHITECTURE_AUDIT.md section 5.2 for why
    # this is deliberately NOT Postgres.
    runtime_state_dir: str = "runtime_state"

    # Session lifetime. Sliding: touched on use, absolute cap below.
    session_idle_seconds: int = 60 * 60 * 24 * 7
    session_absolute_seconds: int = 60 * 60 * 24 * 30

    cookie_name: str = "kynd_session"
    cookie_secure: bool = False  # MUST be True in production; validated below.
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None

    # Kept as a plain comma-separated string, NOT a list[str]. pydantic-settings
    # attempts json.loads() on any complex-typed field sourced from a dotenv or
    # environment variable, BEFORE field validators run — so a `list[str]` here
    # makes `KYND_CORS_ORIGINS=http://localhost:3000` a hard startup crash
    # ("error parsing value for field") rather than the obvious comma-split.
    # Parsing it ourselves in `cors_origins` below keeps the env format the
    # plain one an operator would expect to write.
    cors_origins_raw: str = Field(
        default="http://localhost:3000", alias="KYND_CORS_ORIGINS"
    )

    # Rate limits: max_attempts per window_seconds.
    rate_limit_login_attempts: int = 10
    rate_limit_login_window: int = 300
    rate_limit_signup_attempts: int = 5
    rate_limit_signup_window: int = 3600

    # Slack app-level signing secret (from the Slack app's "Basic Information"
    # page). One value for the whole Kynd deployment: a single Kynd Slack app
    # is what customer workspaces install against, same as any standard Slack
    # app — not per-customer. Verifies X-Slack-Signature on inbound events;
    # never used to decide tenancy (see kynd_api/routers/slack_webhooks.py).
    slack_signing_secret: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def rate_limit_login(self) -> tuple[int, int]:
        return (self.rate_limit_login_attempts, self.rate_limit_login_window)

    @property
    def rate_limit_signup(self) -> tuple[int, int]:
        return (self.rate_limit_signup_attempts, self.rate_limit_signup_window)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def assert_production_safety(self) -> None:
        """Refuse to boot a production deployment with development defaults.

        Called from main.py's startup. A cookie without Secure in production is
        a session token travelling in cleartext on any downgraded request —
        this is the class of mistake that is invisible until it is exploited,
        so it fails the boot instead of logging a warning nobody reads.
        """
        if not self.is_production:
            return
        problems: list[str] = []
        if not self.cookie_secure:
            problems.append("KYND_COOKIE_SECURE must be true in production")
        if "localhost" in self.database_url:
            problems.append("KYND_DATABASE_URL still points at localhost")
        if any("localhost" in origin for origin in self.cors_origins):
            problems.append("KYND_CORS_ORIGINS still contains localhost")
        if problems:
            raise RuntimeError(
                "Refusing to start in production with unsafe configuration:\n  - "
                + "\n  - ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Test hook: forget the cached Settings so env changes take effect."""
    get_settings.cache_clear()


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    s = get_settings()
    print(f"environment      = {s.environment}", file=sys.stderr)
    print(f"database_url     = {s.database_url}", file=sys.stderr)
    print(f"runtime_state    = {s.runtime_state_dir}", file=sys.stderr)
