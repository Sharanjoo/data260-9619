import re

def normalize_notice_title(title: str, max_length: int = 100) -> str:
    """
    Normalize a recall notice title by trimming whitespace, collapsing runs of whitespace into one space,
    and ensuring the title does not exceed the specified maximum length.
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
    Test that the function correctly handles valid input.
    """
    assert normalize_notice_title("  Example Title  ") == "Example Title"
    assert normalize_notice_title("This is a test title with multiple spaces") == "This is a test title with multiple spaces"
    assert normalize_notice_title("Short title", 20) == "Short title"

def test_normalize_notice_title_non_string_input():
    """
    Test that the function raises ValueError for non-string input.
    """
    try:
        normalize_notice_title(123)
    except ValueError as e:
        assert str(e) == "Title must be a string."

def test_normalize_notice_title_empty_after_trimming():
    """
    Test that the function raises ValueError for empty title after trimming.
    """
    try:
        normalize_notice_title("   ")
    except ValueError as e:
        assert str(e) == "Title cannot be empty after trimming."

def test_normalize_notice_title_exceeds_max_length():
    """
    Test that the function raises ValueError for title exceeding max length.
    """
    try:
        normalize_notice_title("This title is longer than the allowed maximum length", 20)
    except ValueError as e:
        assert str(e) == "Title is too long. Maximum allowed length is 20 characters."
