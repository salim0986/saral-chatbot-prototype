"""Custom exceptions for the SARAL Chatbot backend."""


class UnsupportedFormatError(ValueError):
    """Raised when an uploaded file has an unsupported MIME type or extension."""


class ParseError(RuntimeError):
    """Raised when Docling or pandoc fails to parse a document."""


class EmbeddingError(RuntimeError):
    """Raised when the embedding model fails to produce vectors."""


class QdrantError(RuntimeError):
    """Raised when a Qdrant operation fails."""
