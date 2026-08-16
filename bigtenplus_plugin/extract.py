import re

BIG10_NUM_RE = re.compile(r"^BIG10\+\s+(\d+):", re.IGNORECASE)


def extract_channel_number_index(name: str) -> int | None:
    m = BIG10_NUM_RE.match(name or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except (ValueError, IndexError):
        return None