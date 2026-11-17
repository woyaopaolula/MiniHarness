from src.network import parse_port


def test_parse_valid_port() -> None:
    assert parse_port("8080") == 8080
