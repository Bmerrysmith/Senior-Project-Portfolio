"""
FastAPI dependency providers.

The get_store() function is the single swap point for the data layer.
To migrate to Supabase/PostgreSQL:
  - Replace CSVStore with an async DB session factory.
  - Change get_store() to an async generator that yields a session and
    closes it on exit (FastAPI handles the teardown automatically).
  - Update all router Depends() — because the signature stays
    `store: SomeStore = Depends(get_store)`, only this file changes.
"""
from functools import lru_cache
from app.data.csv_store import CSVStore


@lru_cache(maxsize=1)
def get_store() -> CSVStore:
    return CSVStore()
