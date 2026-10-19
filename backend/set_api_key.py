"""Store the AI API key in .env safely.

    python -m backend.set_api_key            # prompts (input hidden), verifies, saves
    python -m backend.set_api_key --no-verify

- The key is typed into a hidden prompt, so it never appears on screen or in shell history.
  Never paste a key into chats, documents or code.
- The provider is detected from the key: "sk-ant-…" → Anthropic, otherwise OpenAI.
- .env is written with permissions 600 (readable only by your user) and is git-ignored.
- Verification only lists/looks up models (free, no tokens used).
"""

import getpass
import os
import sys

from .config import ENV_FILE, PROVIDERS


def _write_env(updates: dict[str, str]) -> None:
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [line for line in lines if line.split("=", 1)[0].strip() not in updates]
    lines += [f"{k}={v}" for k, v in updates.items()]
    # Create with 600 from the start so the key is never world-readable, even briefly.
    fd = os.open(ENV_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(ENV_FILE, 0o600)


def _verify(provider: str, key: str, model: str) -> bool:
    try:
        if provider == "openai":
            import openai as sdk

            sdk.OpenAI(api_key=key, max_retries=1, timeout=20).models.retrieve(model)
        else:
            import anthropic as sdk

            sdk.Anthropic(api_key=key, max_retries=1, timeout=20).models.retrieve(model)
    except sdk.AuthenticationError:
        print("✗ المفتاح غير صالح (رفضه الخادم).")
        return False
    except sdk.NotFoundError:
        print(f"✗ المفتاح صالح، لكن النموذج {model} غير متاح له. غيّر AI_MODEL في .env.")
        return False
    except sdk.APIConnectionError:
        print("! تعذّر الاتصال للتحقق (الإنترنت؟). سيُحفظ المفتاح دون تحقق.")
        return True
    except sdk.APIStatusError as e:
        print(f"! تعذّر التحقق (رمز {e.status_code}). سيُحفظ المفتاح دون تحقق.")
        return True
    print(f"✓ المفتاح يعمل مع النموذج {model}.")
    return True


def main() -> int:
    key = getpass.getpass("الصق مفتاح API (لن يظهر أثناء الكتابة): ").strip()
    if not key:
        print("لم يُدخل أي مفتاح.")
        return 1
    provider = "anthropic" if key.startswith("sk-ant-") else "openai"
    key_var, default_model = PROVIDERS[provider]
    model = os.getenv("AI_MODEL", "").strip() or default_model
    print(f"المزود: {provider}")
    if "--no-verify" not in sys.argv and not _verify(provider, key, model):
        return 1
    _write_env({"AI_PROVIDER": provider, key_var: key})
    print(f"✓ حُفظ المفتاح في {ENV_FILE.name} (صلاحيات 600). أعد تشغيل الخادم ليقرأه.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
