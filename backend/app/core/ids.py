"""UUIDv7 generation — see docs/architecture/00-overview-and-decisions.md ADR-010.

Sequential-enough for index locality, unguessable enough to prevent
enumeration. Generated in the application, not by a database default, so
an object has its identity before it is flushed.
"""

from uuid import UUID

from uuid6 import uuid7


def new_id() -> UUID:
    """Generate a new UUIDv7. Returns a stdlib `uuid.UUID` (uuid6.UUID subclasses it)."""
    return UUID(str(uuid7()))
