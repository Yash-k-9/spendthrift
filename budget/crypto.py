"""Encryption, integrity and signing for stored transactions.

Every transaction is stored as one encrypted blob in a tamper-evident ledger:

  encryption   AES-256-GCM, fresh random 96-bit nonce per record. GCM's auth tag
               makes any change to the ciphertext fail decryption.
  hash chain   record_hash = SHA-256(prev_hash || content_hash || key_version).
               Editing, deleting or reordering a past row breaks every later hash.
  signature    each record_hash is signed with an Ed25519 private key, so the
               chain can't be quietly rebuilt by someone without the key.
  dedupe tag   HMAC-SHA256 of an incoming SMS: spots duplicates without
               storing anything readable.

Keys (never stored in the database):
  LEDGER_KEY          base64, 32 random bytes; the AES and HMAC keys are derived
                      from it with HKDF so each has a single purpose
  LEDGER_SIGNING_KEY  base64, 32-byte Ed25519 private key
Losing them means the data can't be decrypted, so back up your .env.
"""

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

KEY_VERSION = 1
GENESIS_HASH = "0" * 64      # prev_hash of the first record in the chain
NONCE_BYTES = 12


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode())


def _derive(master: bytes, purpose: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=purpose.encode()).derive(master)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def chain_hash(prev_hash: str, content_hash: str, key_version: int) -> str:
    return sha256_hex(f"{prev_hash}|{content_hash}|{key_version}".encode())


@dataclass
class Vault:
    master_key: bytes
    signing_key: Ed25519PrivateKey

    # ---- construction --------------------------------------------------
    @classmethod
    def generate(cls) -> "Vault":
        return cls(os.urandom(32), Ed25519PrivateKey.generate())

    @classmethod
    def from_strings(cls, master_b64: str, signing_b64: str) -> "Vault":
        master = _unb64(master_b64)
        if len(master) != 32:
            raise ValueError("LEDGER_KEY must be 32 bytes (base64-encoded).")
        return cls(master, Ed25519PrivateKey.from_private_bytes(_unb64(signing_b64)))

    def export(self) -> dict[str, str]:
        raw = self.signing_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        return {"LEDGER_KEY": _b64(self.master_key), "LEDGER_SIGNING_KEY": _b64(raw)}

    def __post_init__(self):
        self._aes = AESGCM(_derive(self.master_key, "family-budget/aes-gcm"))
        self._mac_key = _derive(self.master_key, "family-budget/hmac")

    # ---- encryption ----------------------------------------------------
    def encrypt(self, payload: dict, aad: str) -> tuple[str, str]:
        """payload -> (nonce, ciphertext), both base64. aad binds the ciphertext to its context."""
        nonce = os.urandom(NONCE_BYTES)
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        return _b64(nonce), _b64(self._aes.encrypt(nonce, data, aad.encode()))

    def decrypt(self, nonce: str, ciphertext: str, aad: str) -> dict:
        """Raises cryptography.exceptions.InvalidTag if anything was changed."""
        return json.loads(self._aes.decrypt(_unb64(nonce), _unb64(ciphertext), aad.encode()))

    # ---- integrity -----------------------------------------------------
    def mac(self, text: str) -> str:
        return hmac.new(self._mac_key, text.encode(), hashlib.sha256).hexdigest()

    def sign(self, record_hash: str) -> str:
        return _b64(self.signing_key.sign(record_hash.encode()))

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self.signing_key.public_key()

    def verify_signature(self, record_hash: str, signature: str) -> bool:
        try:
            self.public_key.verify(_unb64(signature), record_hash.encode())
            return True
        except Exception:
            return False

    def fingerprints(self) -> dict[str, str]:
        """Short, non-secret identifiers of the keys (safe to display)."""
        pub = self.public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return {"encryption_key": sha256_hex(b"fp" + self.master_key)[:16],
                "signing_public_key": _b64(pub)}
