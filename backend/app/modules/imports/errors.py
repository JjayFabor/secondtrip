"""Import workflow domain errors."""

from fastapi import status

from app.core.errors import ApplicationError, ConflictError


class ImportStateConflictError(ConflictError):
    code = "IMPORT_STATE_CONFLICT"
    title = "Import state conflict"


class DuplicateImportError(ConflictError):
    code = "DUPLICATE_IMPORT"
    title = "Duplicate import"


class InvalidUploadError(ApplicationError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "INVALID_UPLOAD"
    title = "Invalid upload"


class InvalidMappingError(ApplicationError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "INVALID_MAPPING"
    title = "Invalid mapping"
