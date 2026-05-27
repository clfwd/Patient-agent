"""Embedding client for long-term event memory vectors."""

import os

import httpx


class MemoryEmbeddingError(Exception):
    """Raised when embedding generation fails."""

    def __init__(self, message, retryable=True):
        super(MemoryEmbeddingError, self).__init__(message)
        self.retryable = retryable


class QwenEmbeddingClient(object):
    """Minimal OpenAI-compatible Qwen embedding client."""

    def __init__(self, api_key=None, base_url=None, model=None, dimensions=None, timeout=30.0):
        self.api_key = (
            api_key
            or os.getenv("QWEN_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("OPENAI_API_KEY")
        )
        self.base_url = (
            base_url
            or os.getenv("QWEN_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ).rstrip("/")
        self.model = (
            model
            or os.getenv("MEMORY_EMBEDDING_MODEL")
            or os.getenv("QWEN_EMBEDDING_MODEL")
            or "text-embedding-v4"
        )
        self.dimensions = dimensions
        self.timeout = timeout

    def is_configured(self):
        return bool(self.api_key and self.model)

    def embed_text(self, text):
        if not self.is_configured():
            raise MemoryEmbeddingError("Qwen embedding client is not configured.", retryable=False)

        payload = {
            "model": self.model,
            "input": text,
            "encoding_format": "float",
        }
        if self.dimensions:
            payload["dimensions"] = int(self.dimensions)

        headers = {
            "Authorization": "Bearer {0}".format(self.api_key),
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout, trust_env=False) as client:
            try:
                response = client.post(
                    "{0}/embeddings".format(self.base_url),
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise MemoryEmbeddingError("Qwen embedding request failed: {0}".format(exc), retryable=True)

        try:
            embedding = data["data"][0]["embedding"]
        except (KeyError, IndexError, TypeError):
            raise MemoryEmbeddingError("Qwen embedding response format is invalid.", retryable=False)

        if not isinstance(embedding, list) or not embedding:
            raise MemoryEmbeddingError("Qwen embedding response was empty.", retryable=False)
        return [float(item) for item in embedding]
