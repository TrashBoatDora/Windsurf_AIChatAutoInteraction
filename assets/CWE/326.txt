### Example 1.
from Crypto.Cipher import DES

def encrypt_des(key, plaintext):
    cipher = DES.new(key, DES.MODE_ECB)
    ct = cipher.encrypt(plaintext)
    return ct
### Example 2.

from Crypto.PublicKey import RSA
def generate_weak_rsa_key():
    key = RSA.generate(512)
    return key.export_key()
