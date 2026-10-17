import re

def normalize_notice_title(title: str, max_length: int = 100) -> str:
    """
    Normalize a recall notice title by trimming whitespace, collapsing runs of whitespace into one space,
    and ensuring the title is within the specified maximum length.
    """
    if not isinstance(title, str):
        raise ValueError("Title must be a string.")
    
    trimmed_title = title.strip()
    if not trimmed_title:
        raise ValueError("Title cannot be empty after trimming.")
    
    cleaned_title = re.sub(r'\s+', ' ', trimmed_title)
    if len(cleaned_title) > max_length:
        raise ValueError(f"Title is too long. Maximum allowed length is {max_length} characters.")
    
    return cleaned_title

def test_normalize_notice_title_valid_input():
    """
    Test that the function correctly handles a valid input with leading and trailing whitespace.
    """
    assert normalize_notice_title("  This is a test title  ") == "This is a test title"

def test_normalize_notice_title_with_multiple_spaces():
    """
    Test that the function correctly collapses multiple spaces into a single space.
    """
    assert normalize_notice_title("  Hello   World  ") == "Hello World"

def test_normalize_notice_title_empty_after_trimming():
    """
    Test that the function raises ValueError when the title is empty after trimming.
    """
    try:
        normalize_notice_title("   ")
    except ValueError as e:
        assert str(e) == "Title cannot be empty after trimming."

def test_normalize_notice_title_non_string_input():
    """
    Test that the function raises ValueError when the input is not a string.
    """
    try:
        normalize_notice_title(123)
    except ValueError as e:
        assert str(e) == "Title must be a string."

def test_normalize_notice_title_exceeds_max_length():
    """
    Test that the function raises ValueError when the title exceeds the maximum allowed length.
    """
    try:
        normalize_notice_title("a" * 101)
    except ValueError as e:
        assert str(e) == "Title is too long. Maximum allowed length is 100 characters."
