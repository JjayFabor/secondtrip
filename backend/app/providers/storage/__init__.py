"""Object-storage provider boundary. See docs/architecture/10-storage.md."""

from app.providers.storage.base import StorageProvider
from app.providers.storage.types import ObjectMetadata, PresignedUpload, StoredObject

__all__ = ["ObjectMetadata", "PresignedUpload", "StorageProvider", "StoredObject"]
