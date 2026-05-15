from cryptography.fernet import Fernet
import os


def load_or_create_key(key_path: str) -> bytes:
    """Load existing Fernet key or generate and save a new one."""
    os.makedirs(os.path.dirname(key_path), exist_ok=True)
    if os.path.exists(key_path):
        with open(key_path, 'rb') as f:
            return f.read()
    key = Fernet.generate_key()
    with open(key_path, 'wb') as f:
        f.write(key)
    os.chmod(key_path, 0o600)
    return key


def encrypt_file(path: str, fernet: Fernet) -> None:
    """Encrypt a file in place."""
    with open(path, 'rb') as f:
        data = f.read()
    with open(path + '.enc', 'wb') as f:
        f.write(fernet.encrypt(data))
    os.remove(path)


def decrypt_file(enc_path: str, fernet: Fernet) -> bytes:
    """Decrypt an encrypted file, return bytes."""
    with open(enc_path, 'rb') as f:
        return fernet.decrypt(f.read())
