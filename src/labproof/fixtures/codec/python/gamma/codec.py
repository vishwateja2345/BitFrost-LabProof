"""Container-only synthetic byte codec; opaque variant gamma."""


def encode(payload):
    if not isinstance(payload, bytes) or len(payload) >= 256:
        raise ValueError("invalid payload")
    return len(payload).to_bytes(1, "big") + payload


def decode(frame):
    if not isinstance(frame, bytes) or len(frame) < 1:
        raise ValueError("invalid frame")
    length = int.from_bytes(frame[:1], "big")
    if len(frame[1:]) != length:
        raise ValueError("invalid frame")
    return bytes(frame[1:])
