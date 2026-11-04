"""Parse stable Telegram user IDs without confusing them with username fragments."""
import re


def user_id_query(raw: str) -> tuple[bool, int | None]:
    value = (raw or "").strip()
    if value.startswith("@"):
        return False, None
    explicit = re.match(r"^id(?:\s*:\s*|\s+|$)", value, re.IGNORECASE)
    if explicit:
        value = value[explicit.end():].strip()
    numeric = value.isdecimal() or bool(re.fullmatch(r"[+-][0-9]+", value))
    if not explicit and not numeric:
        return False, None
    if not re.fullmatch(r"[0-9]{1,19}", value):
        return True, None
    number = int(value)
    return True, number if 0 < number <= 2**63 - 1 else None


def literal_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
