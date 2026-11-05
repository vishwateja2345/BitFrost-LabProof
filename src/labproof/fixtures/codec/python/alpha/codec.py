"""Container-only synthetic byte codec; opaque variant alpha."""


def encode(payload):
    if type(payload) is not bytes or len(payload) > 255:
        raise ValueError("invalid payload")
    return bytes([len(payload)]) + payload


def decode(frame):
    if type(frame) is not bytes or not frame:
        raise ValueError("invalid frame")
    # Purpose-built defect: length is not checked before returning payload.
    return frame[1:]
