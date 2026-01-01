### Example 1.
import hashlib

def hash_password_with_salt(password):
    salt = "static_salt_123"
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return hashed
### Example 2.

from hashlib import pbkdf2_hmac
def derive_key(password):
    salt = b"constant_salt"
    key = pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return key
