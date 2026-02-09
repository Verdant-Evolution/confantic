"""Autocomplete functionality for JSON/YAML config editing."""

import re
from typing import Optional, Union

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
    # JSON: after "{" or "," look for a new key being typed
    # YAML: at start of line or after ":" look for a new key being typed
    
    # Check if we're typing after a quote (JSON key)
    json_key_match = re.search(r'"([^"]*?)$', before_cursor)
    if json_key_match:
        partial_key = json_key_match.group(1)
        key_start = json_key_match.start(1)
        return partial_key, key_start
    
    # Check if we're typing a YAML key (word at start of line or after whitespace)
    yaml_key_match = re.search(r'^\s*(\w*)$', before_cursor)
    if yaml_key_match:
        partial_key = yaml_key_match.group(1)
        key_start = yaml_key_match.start(1)
        return partial_key, key_start
    
    # Check if we're typing an unquoted JSON/YAML key after colon
    after_colon_match = re.search(r':\s*(\w*)$', before_cursor)
    if after_colon_match:
        # This is likely a value, not a key - don't suggest
        return None, 0
    
    return None, 0


def filter_suggestions(field_names: list[str], partial_key: str) -> list[str]:
    """Filter field names based on the partial key typed by the user."""
    if not partial_key:
        return field_names
    
    # Case-insensitive prefix matching
    partial_lower = partial_key.lower()
    return [name for name in field_names if name.lower().startswith(partial_lower)]
