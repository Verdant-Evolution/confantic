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
    assert sorted(suggestions) == ["address", "age"]
    
    # Test with no match
    suggestions = filter_suggestions(field_names, "xyz")
    assert suggestions == []
    
    # Test with empty prefix (should return all)
    suggestions = filter_suggestions(field_names, "")
    assert suggestions == field_names
    
    # Test case insensitivity
    suggestions = filter_suggestions(field_names, "NA")
    assert suggestions == ["name"]


def test_get_current_context_only_after_typing():
    """Test that autocomplete only triggers after typing at least one character."""
    from confantic.autocomplete import get_current_context
    
    # Just a quote - should NOT trigger
    json_text = '{\n  "'
    cursor_row = 1
    cursor_col = 3
    partial_key, key_start = get_current_context(json_text, cursor_row, cursor_col)
    assert partial_key is None, "Should not trigger with just a quote"
    
    # Quote with one character - SHOULD trigger
    json_text = '{\n  "n'
    cursor_row = 1
    cursor_col = 4
    partial_key, key_start = get_current_context(json_text, cursor_row, cursor_col)
    assert partial_key == "n", "Should trigger after typing one character"


def test_get_existing_keys_in_current_object():
    """Test extraction of existing keys in the current object."""
    from confantic.autocomplete import get_existing_keys_in_current_object
    
    # Test with root object
    json_text = '{\n  "name": "John",\n  "age": 25,\n  "a'
    cursor_row = 3
    cursor_col = 5
    existing = get_existing_keys_in_current_object(json_text, cursor_row, cursor_col)
    assert set(existing) == {"name", "age"}, f"Expected name and age, got {existing}"
    
    # Test with nested object
    nested_json = '{\n  "person": {\n    "name": "John",\n    "n'
    cursor_row = 3
    cursor_col = 7
    existing = get_existing_keys_in_current_object(nested_json, cursor_row, cursor_col)
    assert existing == ["name"], f"Expected only name in nested object, got {existing}"


def test_get_current_object_path():
    """Test detection of current object path for nested objects."""
    from confantic.autocomplete import get_current_object_path
    
    # Test at root level
    json_text = '{\n  "n'
    cursor_row = 1
    cursor_col = 4
    path = get_current_object_path(json_text, cursor_row, cursor_col)
    assert path == [], f"Expected empty path at root, got {path}"
    
    # Test in nested object
    nested_json = '{\n  "address": {\n    "s'
    cursor_row = 2
    cursor_col = 6
    path = get_current_object_path(nested_json, cursor_row, cursor_col)
    assert path == ["address"], f"Expected ['address'], got {path}"


def test_get_nested_model_at_path():
    """Test getting nested model based on path."""
    from confantic.autocomplete import get_nested_model_at_path, get_field_names
    
    class Address(BaseModel):
        street: str
        city: str
        zip_code: str
    
    class Person(BaseModel):
        name: str
        address: Address
    
    # Test getting root model
    root_model = get_nested_model_at_path(Person, [])
    assert root_model == Person
    
    # Test getting nested model
    nested_model = get_nested_model_at_path(Person, ["address"])
    assert nested_model == Address
    
    # Verify we can get fields from nested model
    fields = get_field_names(nested_model)
    assert set(fields) == {"street", "city", "zip_code"}
    
    # Test invalid path
    invalid_model = get_nested_model_at_path(Person, ["nonexistent"])
    assert invalid_model is None
