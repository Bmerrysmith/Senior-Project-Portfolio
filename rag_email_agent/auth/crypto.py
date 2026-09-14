from cryptography.fernet import Fernet

from auth.secrets import get_token_encryption_key

TOKEN_ENCRYPTION_KEY = get_token_encryption_key()


def encrypt(plaintext):
    return Fernet(TOKEN_ENCRYPTION_KEY).encrypt(plaintext.encode()).decode()


def decrypt(ciphertext):
    return Fernet(TOKEN_ENCRYPTION_KEY).decrypt(ciphertext.encode()).decode()
