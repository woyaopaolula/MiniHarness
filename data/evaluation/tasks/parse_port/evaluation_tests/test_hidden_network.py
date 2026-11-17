import pytest

from src.network import parse_port


@pytest.mark.parametrize("value", ["1", "443", "65535"])
def test_accepts_valid_ports(value: str) -> None:
    assert parse_port(value) == int(value)


@pytest.mark.parametrize("value", ["0", "-1", "65536"])
def test_rejects_out_of_range_ports(value: str) -> None:
    with pytest.raises(ValueError):
        parse_port(value)


def test_rejects_non_numeric_value() -> None:
    with pytest.raises(ValueError):
        parse_port("http")
