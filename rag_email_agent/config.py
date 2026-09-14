import os

from dotenv import load_dotenv

from auth.secrets import get_openai_api_key, get_supabase_connection_string

load_dotenv()

CLIENT_ID = os.environ["CLIENT_ID"]
AUTHORITY = os.environ["AUTHORITY"]
REDIRECT_URI = os.environ["REDIRECT_URI"]
GRAPH_SCOPES = os.environ["GRAPH_SCOPES"].split()
FLASK_SECRET_KEY = os.environ["FLASK_SECRET_KEY"]

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

SUPABASE_CONNECTION_STRING = get_supabase_connection_string()

OPENAI_API_KEY = get_openai_api_key()
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

CHUNK_SIZE = int(os.environ.get("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.environ.get("CHUNK_OVERLAP", "200"))

SUMMARIZATION_MODEL = os.environ.get("SUMMARIZATION_MODEL", "gpt-5-mini")
SENDER_CONTEXT_LIMIT = int(os.environ.get("SENDER_CONTEXT_LIMIT", "5"))
GROUNDING_LIMIT = int(os.environ.get("GROUNDING_LIMIT", "5"))
CONTEXT_SNIPPET_CHARS = int(os.environ.get("CONTEXT_SNIPPET_CHARS", "300"))
