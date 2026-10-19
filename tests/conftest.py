import os
import tempfile
from pathlib import Path

# Isolated database and a dummy key, set before the app is imported.
# The real AI is never called in tests: generate_structured is replaced by fakes.
_tmp_dir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_dir) / 'test.db'}"
os.environ["AI_PROVIDER"] = "openai"
os.environ["OPENAI_API_KEY"] = "sk-test-dummy"
