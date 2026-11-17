from src.tags import normalize_tags


def test_normalize_tags() -> None:
    assert normalize_tags("Python, AI") == ["python", "ai"]
