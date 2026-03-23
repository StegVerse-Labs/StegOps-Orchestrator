import json
import base64
from nacl.signing import VerifyKey


def verify_envelope(envelope: dict, trusted_keys: dict) -> bool:
    event = envelope["event"]
    sig = base64.b64decode(envelope["signature"]["value"])
    key_id = envelope["issuer"]["key_id"]

    key = trusted_keys.get(key_id)
    if not key or key["status"] != "active":
        return False

    verify_key = VerifyKey(base64.b64decode(key["public_key"]))

    canonical = json.dumps(event, sort_keys=True, separators=(",", ":")).encode()

    try:
        verify_key.verify(canonical, sig)
        return True
    except Exception:
        return False
