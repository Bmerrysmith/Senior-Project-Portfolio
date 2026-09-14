import json

import boto3

REGION = "us-east-1"

TOKEN_ENCRYPTION_KEY_SECRET_ID = "rag-email-agent/token-encryption-key"
SUPABASE_CONNECTION_STRING_SECRET_ID = "rag-email-agent/supabase-connection-string"
OPENAI_API_KEY_SECRET_ID = "rag-email-agent/openai-api-key"


def _get_secret(secret_id, key):
    client = boto3.client("secretsmanager", region_name=REGION)
    response = client.get_secret_value(SecretId=secret_id)
    return json.loads(response["SecretString"])[key]


def get_token_encryption_key():
    return _get_secret(TOKEN_ENCRYPTION_KEY_SECRET_ID, "TOKEN_ENCRYPTION_KEY")


def get_supabase_connection_string():
    return _get_secret(SUPABASE_CONNECTION_STRING_SECRET_ID, "SUPABASE_CONNECTION_STRING")


def get_openai_api_key():
    return _get_secret(OPENAI_API_KEY_SECRET_ID, "OPENAI_API_KEY")
