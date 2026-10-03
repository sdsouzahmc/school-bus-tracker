"""Simulated bus-device storage (spec §6): encrypted roster and a durable, encrypted offline queue that survives an app restart."""
import base64
import hashlib
import json
import os
import secrets

from cryptography.fernet import Fernet, InvalidToken

import db

STORE = os.path.join(os.path.dirname(db.DB_PATH) or ".", "device_store")


def _key(device_id):
    master = db.setting("device_master_key")
    if not master:
        master = secrets.token_hex(32)
        db.set_setting("device_master_key", master)
    return base64.urlsafe_b64encode(hashlib.sha256(f"{master}:{device_id}".encode()).digest())


def _path(device_id):
    os.makedirs(STORE, exist_ok=True)
    return os.path.join(STORE, f"queue_device_{device_id}.bin")


def load_queue(device_id):
    p = _path(device_id)
    if not os.path.exists(p):
        return []
    try:
        return json.loads(Fernet(_key(device_id)).decrypt(open(p, "rb").read()))
    except (InvalidToken, ValueError):
        return []


def save_queue(device_id, items):
    with open(_path(device_id), "wb") as f:
        f.write(Fernet(_key(device_id)).encrypt(json.dumps(items).encode()))


def encrypted_roster(device_id, payload):
    return Fernet(_key(device_id)).encrypt(json.dumps(payload, default=str).encode())


def decrypt_roster(device_id, blob):
    return json.loads(Fernet(_key(device_id)).decrypt(blob))
