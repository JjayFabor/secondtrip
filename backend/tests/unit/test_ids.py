from uuid import UUID

from app.core.ids import new_id


def test_new_id_is_a_valid_uuid7() -> None:
    value = new_id()
    assert isinstance(value, UUID)
    assert value.version == 7


def test_new_id_is_time_ordered() -> None:
    ids = [str(new_id()) for _ in range(50)]
    assert ids == sorted(ids), "UUIDv7 must sort lexicographically in generation order"


def test_new_id_is_unique() -> None:
    ids = {new_id() for _ in range(1000)}
    assert len(ids) == 1000
