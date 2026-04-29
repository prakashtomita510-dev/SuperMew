from __future__ import annotations

import os
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
load_dotenv(REPO_ROOT / ".env")


def main() -> int:
    client = OpenAI(
        api_key=os.getenv("ARK_API_KEY"),
        base_url=os.getenv("BASE_URL"),
    )
    response = client.chat.completions.create(
        model=os.getenv("MODEL"),
        messages=[{"role": "user", "content": "reply with OK only"}],
        temperature=0,
        max_tokens=8,
    )
    print(response.choices[0].message.content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
