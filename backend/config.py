"""Server-side settings, read from the environment / .env.

The AI API key lives only here, on the server. It is never sent to the browser,
never written to the database and never included in logs or error responses.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Real environment variables take precedence over the .env file.
load_dotenv(ENV_FILE, override=False)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/platform.db")

PROVIDERS = {
    # provider: (API key variable, default model)
    "openai": ("OPENAI_API_KEY", "gpt-5.5"),
    "anthropic": ("ANTHROPIC_API_KEY", "claude-opus-5-5"),
}

AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
if AI_PROVIDER not in PROVIDERS:
    raise RuntimeError(f"AI_PROVIDER must be one of {sorted(PROVIDERS)}, got {AI_PROVIDER!r}")

_key_var, _default_model = PROVIDERS[AI_PROVIDER]
AI_API_KEY = os.getenv(_key_var, "").strip()
AI_MODEL = os.getenv("AI_MODEL", "").strip() or _default_model
# Reasoning depth. OpenAI: minimal | low | medium | high. Anthropic: low | medium | high | xhigh | max.
AI_EFFORT = os.getenv("AI_EFFORT", "high").strip()
# Quicker turns inside learning activities (chat replies, deliverable reviews), where waiting hurts the game.
AI_FAST_EFFORT = os.getenv("AI_FAST_EFFORT", "medium").strip()
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "300"))


def ai_configured() -> bool:
    return bool(AI_API_KEY)
