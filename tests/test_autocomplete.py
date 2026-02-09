"""Test autocomplete functionality."""

import pytest
from confantic.autocomplete import (
    get_field_names,
    get_current_context,
    filter_suggestions,
)
from pydantic import BaseModel


class SimpleModel(BaseModel):
    name: str
    age: int
    email: str
    address: str


def test_get_field_names():
    """Test extracting field names from a Pydantic model."""
    field_names = get_field_names(SimpleModel)
    assert field_names == ["name", "age", "email", "address"]


def test_get_current_context_json():
    """Test detecting context when typing JSON keys."""
    # Test typing inside quotes
    json_text = '{\n  "n'
    cursor_row = 1
    cursor_col = 4
    partial_key, key_start = get_current_context(json_text, cursor_row, cursor_col)
    assert partial_key == "n"
    assert key_start == 3
    
    # Test typing more characters
    json_text = '{\n  "nam'
    cursor_row = 1
    cursor_col = 6
    partial_key, key_start = get_current_context(json_text, cursor_row, cursor_col)
    assert partial_key == "nam"
    assert key_start == 3


def test_get_current_context_yaml():
    """Test detecting context when typing YAML keys."""
    # Test typing at start of line
    yaml_text = 'nam'
    cursor_row = 0
    cursor_col = 3
    partial_key, key_start = get_current_context(yaml_text, cursor_row, cursor_col)
    assert partial_key == "nam"
    assert key_start == 0
    
    # Test typing with indentation
    yaml_text = '  age'
    cursor_row = 0
    cursor_col = 5
    partial_key, key_start = get_current_context(yaml_text, cursor_row, cursor_col)
    assert partial_key == "age"
    assert key_start == 2


def test_get_current_context_not_a_key():
    """Test that we don't detect keys when typing values."""
    # After colon (value position)
    text = 'name: '
    cursor_row = 0
    cursor_col = 6
    partial_key, key_start = get_current_context(text, cursor_row, cursor_col)
    assert partial_key is None
    
    # In the middle of a value
    text = 'name: john'
    cursor_row = 0
    cursor_col = 10
    partial_key, key_start = get_current_context(text, cursor_row, cursor_col)
    assert partial_key is None


def test_filter_suggestions():
    """Test filtering suggestions based on partial input."""
    field_names = ["name", "age", "email", "address"]
    
    # Test with prefix
    suggestions = filter_suggestions(field_names, "na")
    assert suggestions == ["name"]
    
    # Test with prefix matching multiple
    suggestions = filter_suggestions(field_names, "a")
    assert set(suggestions) == {"age", "address"}
    
    # Test with no match
    suggestions = filter_suggestions(field_names, "xyz")
    assert suggestions == []
    
    # Test with empty prefix (should return all)
    suggestions = filter_suggestions(field_names, "")
    assert suggestions == field_names
    
    # Test case insensitivity
    suggestions = filter_suggestions(field_names, "NA")
    assert suggestions == ["name"]
