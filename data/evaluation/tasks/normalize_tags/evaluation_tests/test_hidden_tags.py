from src.tags import normalize_tags


def test_normalizes_case_and_whitespace() -> None:
    assert normalize_tags(" Python , DATA Science ") == [
        "python",
        "data science",
    ]


def test_discards_empty_tags() -> None:
    assert normalize_tags("one, ,, TWO,") == ["one", "two"]


def test_empty_input_returns_empty_list() -> None:
    assert normalize_tags("") == []
