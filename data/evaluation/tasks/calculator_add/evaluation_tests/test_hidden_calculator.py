from src.calculator import add


def test_add_positive_numbers() -> None:
    assert add(10, 5) == 15


def test_add_negative_numbers() -> None:
    assert add(-4, 3) == -1


def test_add_zero() -> None:
    assert add(0, 0) == 0
