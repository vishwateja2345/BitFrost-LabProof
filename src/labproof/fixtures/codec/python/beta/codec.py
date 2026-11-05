"""Container-only synthetic byte codec; opaque variant beta."""


def encode(payload):
    if type(payload) is not bytes or len(payload) > 255:
        raise ValueError("invalid payload")
    return bytes([len(payload)]) + payload


def decode(frame):
    if type(frame) is not bytes or not frame or frame[0] != len(frame) - 1:
        raise ValueError("invalid frame")
    return frame[1:]
