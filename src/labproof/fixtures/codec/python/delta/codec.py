"""Container-only synthetic byte codec; opaque variant delta."""


def encode(payload):
    raise RuntimeError("unavailable")


def decode(frame):
    raise RuntimeError("unavailable")
