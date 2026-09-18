import inspect
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import TenantContext
from app.db.repository import TenantRepository


def test_tenant_context_requires_organization_id() -> None:
    with pytest.raises(TypeError):
        TenantContext()  # type: ignore[call-arg]


def test_tenant_context_defaults_role_and_actor_to_none_for_system_actors() -> None:
    ctx = TenantContext(organization_id=uuid4())
    assert ctx.actor_user_id is None
    assert ctx.role is None


def test_tenant_context_is_frozen() -> None:
    ctx = TenantContext(organization_id=uuid4())
    with pytest.raises((AttributeError, TypeError)):
        ctx.organization_id = uuid4()  # type: ignore[misc]


def test_tenant_repository_cannot_be_constructed_without_a_tenant_context() -> None:
    """CLAUDE.md rule 2 / docs/architecture/02-multi-tenancy.md §2 rule 2:
    a TenantRepository cannot be constructed without a TenantContext. This
    is enforced by `tenant` having no default in __init__ — verified here
    both as a runtime check and by inspecting the signature, so the test
    still fails if a future edit quietly adds a default."""
    params = inspect.signature(TenantRepository.__init__).parameters
    assert params["tenant"].default is inspect.Parameter.empty

    # The TypeError under test fires on the missing `tenant` argument
    # before `session` is ever used — cast() tells mypy to trust the
    # (deliberately never-dereferenced) placeholder's type.
    fake_session = cast(AsyncSession, object())
    with pytest.raises(TypeError):
        TenantRepository(session=fake_session)  # type: ignore[call-arg]
