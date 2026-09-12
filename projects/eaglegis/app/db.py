"""
Supabase client singleton.
Reads SUPABASE_URL and SUPABASE_KEY from environment variables.
Set these in Railway → Variables before deploying.
"""
from functools import lru_cache
from typing import Optional

from supabase import Client, create_client

from app.config import settings


@lru_cache(maxsize=1)
def get_client() -> Client:
    """Return the configured client or raise if env vars are missing."""
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY environment variables must be set."
        )
    return create_client(settings.supabase_url, settings.supabase_key)


def try_get_client() -> Optional[Client]:
    """Return the configured client, or ``None`` if env vars are missing.

    Used by pipeline stages that should skip silently when Supabase isn't
    configured (e.g. local dev without credentials) rather than raising.
    """
    if not settings.supabase_url or not settings.supabase_key:
        return None
    return get_client()
