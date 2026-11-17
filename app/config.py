from dataclasses import dataclass
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    database_url: str
    mini_app_url: str = ""


def _mini_app_url() -> str:
    value = os.getenv("MINI_APP_URL", "").strip().rstrip("/")
    if not value:
        domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
        value = f"https://{domain}/app" if domain else ""
    if value:
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("MINI_APP_URL must be an HTTPS URL without credentials, query or fragment")
    return value


def _parse_admin_ids(raw: str) -> set[int]:
    result: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if item:
            result.add(int(item))
    return result


settings = Settings(
    bot_token=os.environ["BOT_TOKEN"],
    admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
    database_url=os.environ["DATABASE_URL"],
    mini_app_url=_mini_app_url(),
)
