from Crypto.Cipher import AES
import base64
import os
from Crypto.Protocol.KDF import scrypt

# Generate a key using a secure password (e.g., environment variable or secrets manager)
password = os.environ.get("EMAIL_CONFIG_ENCRYPTION_PASSWORD", "your_secret_password_to_generate_key").encode("utf-8")
salt = os.environ.get("EMAIL_CONFIG_ENCRYPTION_SALT", "some_random_salt").encode("utf-8")
key = scrypt(password, salt, key_len=32, N=2**14, r=8, p=1)

# Encryption function
def encrypt_password(plain_password):
    if plain_password is None:
        return ""
    cipher = AES.new(key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(str(plain_password).encode())
    return base64.b64encode(cipher.nonce + tag + ciphertext).decode('utf-8')

# Decryption function
def decrypt_password(encrypted_password):
    if not encrypted_password:
        return ""
    try:
        encrypted_data = base64.b64decode(encrypted_password)
        nonce, tag, ciphertext = encrypted_data[:16], encrypted_data[16:32], encrypted_data[32:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag).decode('utf-8')
    except Exception:
        # Backward compatibility for rows that were historically stored as plain text.
        return encrypted_password

# # Example usage
# password_to_store = "user_password"
# encrypted_password = encrypt_password(password_to_store)
# print("Encrypted:", encrypted_password)

# # When needed to connect
# decrypted_password = decrypt_password(encrypted_password)
# print("Decrypted:", decrypted_password)