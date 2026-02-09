"""Autocomplete functionality for JSON/YAML config editing."""

import json
import re
from typing import Optional, Union

import yaml
from pydantic import BaseModel, TypeAdapter
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import OptionList
from textual.widget import Widget
from textual.geometry import Offset


class AutocompletePopup(Container):
    """A popup widget that displays autocomplete suggestions."""

    DEFAULT_CSS = """
    AutocompletePopup {
        layer: overlay;
        width: auto;
        height: auto;
        max-height: 10;
        background: $surface;
        border: solid $primary;
        display: none;
    }
    
    AutocompletePopup > OptionList {
        width: 30;
        height: auto;
        max-height: 10;
        background: $surface;
        border: none;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.option_list = OptionList()

    def compose(self) -> ComposeResult:
        yield self.option_list

    def show_suggestions(self, suggestions: list[str], position: Offset):
        """Show the popup with suggestions at the given position."""
        if not suggestions:
            self.hide_popup()
            return

        self.option_list.clear_options()
        for suggestion in suggestions:
            self.option_list.add_option(suggestion)
        
        # Position the popup
        self.styles.offset = (position.x, position.y)
        self.styles.display = "block"
        
        # Highlight first option
        if len(suggestions) > 0:
            self.option_list.highlighted = 0

    def hide_popup(self):
        """Hide the popup."""
        self.styles.display = "none"
        self.option_list.clear_options()

    def get_selected_suggestion(self) -> Optional[str]:
        """Get the currently highlighted suggestion."""
        if self.option_list.highlighted is not None:
            option = self.option_list.get_option_at_index(self.option_list.highlighted)
            if option is not None:
                return str(option.prompt)
        return None

    def navigate_up(self):
        """Navigate to the previous suggestion."""
        if self.option_list.option_count > 0:
            self.option_list.action_cursor_up()

    def navigate_down(self):
        """Navigate to the next suggestion."""
        if self.option_list.option_count > 0:
            self.option_list.action_cursor_down()


def get_field_names(model: Union[type[BaseModel], TypeAdapter]) -> list[str]:
    """Extract all field names from a Pydantic model."""
    if isinstance(model, TypeAdapter):
        # For TypeAdapter, we can't extract field names easily
        return []
    
    if isinstance(model, type) and issubclass(model, BaseModel):
        return list(model.model_fields.keys())
    
    return []


def get_current_context(text: str, cursor_row: int, cursor_col: int) -> tuple[Optional[str], int]:
    """
    Determine the current editing context at the cursor position.
    
    Returns:
        A tuple of (partial_key, key_start_col) where:
        - partial_key is the partially typed key name, or None if not typing a key
        - key_start_col is the column where the key started
    """
    lines = text.split('\n')
    if cursor_row >= len(lines):
        return None, 0
    
    current_line = lines[cursor_row]
    before_cursor = current_line[:cursor_col]
    
    # Try to detect if we're typing a key in JSON or YAML
    # Priority: Check for value position first (after colon), then check for key positions
    
    # Check if we're typing a value (after colon) - don't suggest keys here
    after_colon_match = re.search(r':\s*(\w*)$', before_cursor)
    if after_colon_match:
        # This is likely a value, not a key - don't suggest
        return None, 0
    
    # Check if we're typing after a quote (JSON key)
    # Modified to only trigger if there's actual content after the quote
    json_key_match = re.search(r'"([^"]*?)$', before_cursor)
    if json_key_match:
        partial_key = json_key_match.group(1)
        # Only return if there's at least one character typed after the quote
        # This fixes issue #2 - only show autocomplete after user starts typing
        if len(partial_key) > 0:
            key_start = json_key_match.start(1)
            return partial_key, key_start
        else:
            # Just a quote with no content - don't trigger autocomplete yet
            return None, 0
    
    # Check if we're typing a YAML key (word at start of line or after whitespace)
    yaml_key_match = re.search(r'^\s*(\w+)$', before_cursor)
    if yaml_key_match:
        partial_key = yaml_key_match.group(1)
        key_start = yaml_key_match.start(1)
        return partial_key, key_start
    
    return None, 0


def filter_suggestions(field_names: list[str], partial_key: str) -> list[str]:
    """Filter field names based on the partial key typed by the user."""
    if not partial_key:
        return field_names
    
    # Case-insensitive prefix matching
    partial_lower = partial_key.lower()
    return [name for name in field_names if name.lower().startswith(partial_lower)]


def get_existing_keys_in_current_object(text: str, cursor_row: int, cursor_col: int) -> list[str]:
    """
    Extract keys that already exist in the current JSON/YAML object.
    
    Returns a list of key names that are already present in the current
    object scope (not nested objects or parent objects).
    """
    lines = text.split('\n')
    if cursor_row >= len(lines):
        return []
    
    # Find the start of the current object by looking backwards for '{'
    object_start_row = cursor_row
    brace_depth = 0
    found_start = False
    
    for i in range(cursor_row, -1, -1):
        line = lines[i]
        # Check only up to cursor position on current line
        check_line = line if i < cursor_row else line[:cursor_col]
        
        # Process characters from right to left
        for j in range(len(check_line) - 1, -1, -1):
            char = check_line[j]
            if char == '}':
                brace_depth += 1
            elif char == '{':
                if brace_depth == 0:
                    # Found our object start
                    object_start_row = i
                    found_start = True
                    break
                else:
                    brace_depth -= 1
        
        if found_start:
            break
    
    if not found_start:
        # Couldn't find object start, use beginning
        object_start_row = 0
    
    # Find the end of the current object (or use cursor as end for now)
    # We'll look from object_start to cursor_row
    object_lines = []
    for i in range(object_start_row, cursor_row + 1):
        if i == cursor_row:
            # Include up to cursor on current line
            object_lines.append(lines[i][:cursor_col])
        else:
            object_lines.append(lines[i])
    
    object_text = '\n'.join(object_lines)
    
    # Extract keys from this specific level only
    # We need to be careful not to extract keys from nested objects
    # Simple approach: extract keys and then filter out those inside nested braces
    
    keys = []
    brace_depth = 0
    i = 0
    while i < len(object_text):
        char = object_text[i]
        
        if char == '{':
            brace_depth += 1
            i += 1
            continue
        elif char == '}':
            brace_depth -= 1
            i += 1
            continue
        
        # Only look for keys at depth 1 (inside our object but not nested)
        if brace_depth == 1:
            # Try to match a key pattern from this position
            # For JSON: "key":
            json_match = re.match(r'"([^"]+)"\s*:', object_text[i:])
            if json_match:
                keys.append(json_match.group(1))
                i += len(json_match.group(0))
                continue
            
            # For YAML: word at start of line followed by colon
            # Check if we're at start of line or after newline
            if i == 0 or object_text[i-1] == '\n':
                yaml_match = re.match(r'\s*(\w+)\s*:', object_text[i:])
                if yaml_match:
                    keys.append(yaml_match.group(1))
                    i += len(yaml_match.group(0))
                    continue
        
        i += 1
    
    return keys


def get_nested_model_at_path(model: Union[type[BaseModel], TypeAdapter], path: list[str]) -> Optional[Union[type[BaseModel], TypeAdapter]]:
    """
    Get the nested model at the given path.
    
    Args:
        model: The root Pydantic model
        path: List of field names representing the path to the nested object
        
    Returns:
        The nested model if found, otherwise None
    """
    if isinstance(model, TypeAdapter) or not path:
        return model
    
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        return None
    
    current_model = model
    for field_name in path:
        if not hasattr(current_model, 'model_fields'):
            return None
            
        if field_name not in current_model.model_fields:
            return None
        
        field_info = current_model.model_fields[field_name]
        field_type = field_info.annotation
        
        # Check if it's a BaseModel
        if isinstance(field_type, type) and issubclass(field_type, BaseModel):
            current_model = field_type
        else:
            # Not a nested model
            return None
    
    return current_model


def get_current_object_path(text: str, cursor_row: int, cursor_col: int) -> list[str]:
    """
    Determine the path to the current object being edited.
    
    Returns a list of field names representing the nesting path,
    e.g., [] for root, ['address'] for inside an address object.
    """
    lines = text.split('\n')
    if cursor_row >= len(lines):
        return []
    
    path = []
    brace_count = 0
    
    # Walk backwards from cursor to build the path
    for i in range(cursor_row, -1, -1):
        line = lines[i]
        # Only check up to cursor on current line
        check_line = line if i < cursor_row else line[:cursor_col]
        
        # Count braces
        for j in range(len(check_line) - 1, -1, -1):
            char = check_line[j]
            if char == '}':
                brace_count += 1
            elif char == '{':
                brace_count -= 1
                
                # Found an opening brace - look for the key before it
                if brace_count < 0:
                    # Look backwards from this brace to find the key
                    before_brace = check_line[:j]
                    # Try to find "key": { pattern
                    key_match = re.search(r'"([^"]+)"\s*:\s*$', before_brace)
                    if key_match:
                        path.insert(0, key_match.group(1))
                    else:
                        # Try YAML pattern: key: { or just key:\n  {
                        key_match = re.search(r'(\w+)\s*:\s*$', before_brace)
                        if key_match:
                            path.insert(0, key_match.group(1))
                    brace_count = 0  # Reset for next level
    
    return path
