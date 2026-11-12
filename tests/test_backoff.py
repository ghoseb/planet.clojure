import pytest

from planet.backoff import CAP_S, GRACE_S, delay_s, is_due

HOUR = 3600.0


def test_delay_doubles_from_one_hour_up_to_the_cap() -> None:
    assert [delay_s(n) / HOUR for n in range(1, 9)] == [1, 2, 4, 8, 16, 32, 64, 72]
    assert delay_s(1000) == CAP_S == 72 * HOUR


def test_delay_needs_a_failure() -> None:
    with pytest.raises(ValueError, match="failures"):
        delay_s(0)


def test_is_due() -> None:
    assert is_due(None, now=0.0)
    assert is_due(100.0, now=100.0)
    assert is_due(100.0 + GRACE_S, now=100.0)
    assert not is_due(100.0 + GRACE_S + 1, now=100.0)
