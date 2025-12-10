from cryptography.fernet import Fernet
import os
import base64

def generate_key():
    """
    Generates a key and save it into a file
    """
    key = Fernet.generate_key()
    with open("secret.key", "wb") as key_file:
        key_file.write(key)

def load_key():
    """
    Load the previously generated key
    """
    # In production, load from env or secure vault
    if os.path.exists("secret.key"):
        return open("secret.key", "rb").read()
    else:
        # Fallback for dev if file doesn't exist (create one)
        key = Fernet.generate_key()
        with open("secret.key", "wb") as key_file:
            key_file.write(key)
        return key

def encrypt_password(password):
    key = load_key()
    f = Fernet(key)
    return f.encrypt(password.encode()).decode()

def decrypt_password(encrypted_password):
    key = load_key()
    f = Fernet(key)
    return f.decrypt(encrypted_password.encode()).decode()
