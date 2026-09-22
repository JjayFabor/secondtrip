from fastapi import status

from app.core.errors import ApplicationError


class LastOwnerError(ApplicationError):
    """See docs/architecture/02-multi-tenancy.md §3: an org must always
    have at least one active owner. Transfer ownership first."""

    status_code = status.HTTP_409_CONFLICT
    code = "LAST_OWNER"
    title = "Cannot remove the last owner"


class InvitationEmailMismatchError(ApplicationError):
    """See 03-authentication.md §4: an invitation is bound to the
    invited email address; a forwarded link doesn't grant a stranger
    access."""

    status_code = status.HTTP_403_FORBIDDEN
    code = "INVITATION_EMAIL_MISMATCH"
    title = "This invitation was sent to a different email address"
