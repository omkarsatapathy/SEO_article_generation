import os

from dotenv import load_dotenv

# Load .env first so real keys take precedence; fall back to dummies only when
# the keys are genuinely absent (e.g. in CI without a .env file).
load_dotenv(override=False)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("SERPAPI_KEY", "test-serpapi-key")
