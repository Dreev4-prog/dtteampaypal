from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: set[int]
    database_url: str


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
)
