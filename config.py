import os
import sys
import warnings
from pathlib import Path

from dotenv import load_dotenv

warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message="`langchain-community` is being sunset.*",
)

load_dotenv()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PAPERS_DIR = Path(os.getenv("PAPERS_DIR", "papers"))
VECTOR_DB_DIR = Path(os.getenv("VECTOR_DB_DIR", "vector_db"))

AI_BASE_URL = (
    os.getenv("AI_PLATFORM_BASE_URL")
    or os.getenv("SAI_PLATFORM_BASE_URL")
    or "https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1"
)
AI_MODEL = (
    os.getenv("AI_PLATFORM_MODEL")
    or os.getenv("SAI_PLATFORM_MODEL")
    or "qwen/qwen3-5-27b"
)

EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "2"))
RETRIEVAL_FETCH_K = int(os.getenv("RETRIEVAL_FETCH_K", "20"))
MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "1.35"))
DEBUG_RETRIEVAL = os.getenv("DEBUG_RETRIEVAL", "false").lower() in {
    "1",
    "true",
    "yes",
    "y",
}
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "2500"))
SHOW_USAGE = os.getenv("SHOW_USAGE", "true").lower() in {"1", "true", "yes", "y"}
ANSWER_LANGUAGE = os.getenv("ANSWER_LANGUAGE", "vi").lower()

API_KEY_ENV_NAMES = (
    "AI_PLATFORM_API_KEY",
    "SAI_PLATFORM_API_KEY",
    "OPEN_API_KEY",
    "OPENAI_API_KEY",
)


def get_api_key() -> str:
    for env_name in API_KEY_ENV_NAMES:
        api_key = os.getenv(env_name)
        if api_key:
            if env_name == "OPEN_API_KEY":
                print(
                    "Using OPEN_API_KEY from .env. For this provider, prefer "
                    "AI_PLATFORM_API_KEY."
                )
            return api_key

    raise RuntimeError(
        "Missing API key. Add AI_PLATFORM_API_KEY=your_key_here to your .env file."
    )


def make_embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(
        model=EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True},
    )
