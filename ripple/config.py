"""Connection + runtime configuration for Ripple."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    gms_url: str
    gms_token: str | None
    anthropic_api_key: str | None
    gemini_api_key: str | None
    # how many downstream hops to walk when tracing blast radius
    max_lineage_hops: int = 5
    # tag applied to a broken asset on write-back
    incident_tag: str = "incident"

    @classmethod
    def from_env(cls) -> "Config":
        gms_url = os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
        return cls(
            gms_url=gms_url,
            gms_token=os.environ.get("DATAHUB_GMS_TOKEN") or None,
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
            gemini_api_key=os.environ.get("GEMINI_API_KEY") or None,
        )
