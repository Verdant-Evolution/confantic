import json
from pathlib import Path
from typing import Literal, Sequence, Union, Optional

import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static, TextArea
from textual.geometry import Offset

from .lib import Parser, get_model_default, render_type_name
from .validate import validate
from .autocomplete import (
    AutocompletePopup,
    get_field_names,
    get_current_context,
    filter_suggestions,
    get_existing_keys_in_current_object,
    get_current_object_path,
    get_nested_model_at_path,
)

ParseFormat = Literal["json", "yaml"]

PARSER_MAP = {
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}


PARSERS: dict[str, Parser] = {
    "json": Parser(json.loads, lambda d: json.dumps(d, indent=2)),
    "yaml": Parser(yaml.safe_load, lambda d: yaml.safe_dump(d, sort_keys=False)),
}


class ValidationErrorPanel(Static):
    def update_errors(self, errors: str = ""):
        self.update(errors)


class Editor(App):
    CSS_PATH = None
    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+v", "validate", "Validate"),
        ("f5", "validate", "Validate"),
        ("escape", "hide_autocomplete", "Hide autocomplete"),
        ("tab", "accept_suggestion", "Accept suggestion"),
    ]

    def __init__(
        self,
        model: Union[type[BaseModel], TypeAdapter],
        file_path: Union[Path, str],
        force_format: Optional[ParseFormat] = None,
        force_clean: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.model = model
        self.file_path = Path(file_path)
        self.force_clean = force_clean

        parser = PARSERS.get(force_format or self.file_path.suffix.lstrip("."), None)
        if parser is None:
            raise ValueError("Unsupported file format")
        self.parser = parser

        # Set syntax highlighting based on file type
        if force_format == "json" or self.file_path.suffix == ".json":
            self.syntax = "json"
        else:
            self.syntax = "yaml"

        self.validation_panel = ValidationErrorPanel()
        self.text_area = TextArea(language=self.syntax)
        self.autocomplete_popup = AutocompletePopup()
        self.autocomplete_enabled = True
        self.skip_next_autocomplete = False
        self.field_names = get_field_names(model)

        self.title = "Confantic"
        self.sub_title = f"{self.file_path.name} ({render_type_name(model)})"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield self.text_area
            yield self.validation_panel
        yield self.autocomplete_popup
        yield Footer()

    def on_mount(self):
        initial_content = ""
        if not self.force_clean:
            if self.file_path.exists():
                initial_content = self.file_path.read_text()
            else:
                try:
                    data = get_model_default(self.model)
                    initial_content = self.parser.unparse(data)
                except Exception as e:
                    initial_content = ""
                    self.notify(
                        f"Default serialization failed for {render_type_name(self.model)}",
                        severity="error",
                        timeout=4,
                    )

        self.text_area.text = initial_content
        self.action_validate()

    def format_validation_errors(self, ve: ValidationError) -> str:
        lines = []
        model_fields = getattr(self.model, "__fields__", {})
        for err in ve.errors():
            loc: Sequence[Union[int, str]] = err.get("loc", [])
            loc_str = ".".join(str(x) for x in loc)
            msg = err.get("msg", "")
            typ = err.get("type", "")

            # If missing and required, show expected type
            if typ == "missing" and loc:
                field = model_fields.get(loc[0])
                if field is not None:
                    expected_type = field.annotation
                    msg += f" (expected type: {expected_type.__name__ if hasattr(expected_type, '__name__') else expected_type})"
            lines.append(f"- {loc_str}: {msg} [{typ}]")
        return "\n".join(lines)

    def action_validate(self):
        text = self.text_area.text
        try:
            validate(self.model, self.parser.parse(text))
            self.validation_panel.update_errors("")
        except json.JSONDecodeError as e:
            self.validation_panel.update_errors(
                f"JSON parsing error at line {e.lineno}, column {e.colno}: {e.msg}"
            )
        except yaml.YAMLError as e:
            self.validation_panel.update_errors(f"YAML parsing error: {str(e)}")
        except ValidationError as ve:
            self.validation_panel.update_errors(self.format_validation_errors(ve))
        except Exception as e:
            self.validation_panel.update_errors(f"Error: {e}")

    def action_save(self):
        self.file_path.write_text(self.text_area.text)
        self.action_validate()
        self.notify("File saved.", timeout=2)

    def on_text_area_changed(self, event: TextArea.Changed):
        """Handle text changes in the editor to show autocomplete suggestions."""
        if not self.autocomplete_enabled:
            return
        
        # Skip if we just accepted a suggestion
        if self.skip_next_autocomplete:
            self.skip_next_autocomplete = False
            return
        
        # Get cursor position
        cursor_location = self.text_area.selection.end
        cursor_row, cursor_col = cursor_location
        
        # Get current context
        partial_key, key_start_col = get_current_context(
            self.text_area.text, cursor_row, cursor_col
        )
        
        if partial_key is not None:
            # Get the current object path (for nested objects)
            object_path = get_current_object_path(
                self.text_area.text, cursor_row, cursor_col
            )
            
            # Get the appropriate model for the current nesting level
            current_model = get_nested_model_at_path(self.model, object_path)
            
            if current_model is not None:
                # Get field names for the current model
                field_names = get_field_names(current_model)
                
                # Get existing keys in the current object to filter them out
                existing_keys = get_existing_keys_in_current_object(
                    self.text_area.text, cursor_row, cursor_col
                )
                
                # Filter out existing keys
                available_fields = [f for f in field_names if f not in existing_keys]
                
                # Filter suggestions based on partial input
                suggestions = filter_suggestions(available_fields, partial_key)
                
                if suggestions:
                    # Calculate popup position
                    # Position it near the cursor
                    cursor_screen_offset = self.text_area.cursor_screen_offset
                    position = Offset(cursor_screen_offset.x, cursor_screen_offset.y + 1)
                    
                    self.autocomplete_popup.show_suggestions(suggestions, position)
                    return
        
        # Hide popup if no suggestions
        self.autocomplete_popup.hide_popup()

    def action_hide_autocomplete(self):
        """Hide the autocomplete popup."""
        self.autocomplete_popup.hide_popup()

    def action_accept_suggestion(self):
        """Accept the current autocomplete suggestion."""
        # Only accept if popup is visible
        if self.autocomplete_popup.styles.display != "block":
            return
            
        suggestion = self.autocomplete_popup.get_selected_suggestion()
        if suggestion:
            # Set flag to skip next autocomplete trigger
            self.skip_next_autocomplete = True
            
            # Get cursor position
            cursor_location = self.text_area.selection.end
            cursor_row, cursor_col = cursor_location
            
            # Get current context to determine what to replace
            partial_key, key_start_col = get_current_context(
                self.text_area.text, cursor_row, cursor_col
            )
            
            if partial_key is not None:
                # Replace the partial key with the suggestion
                lines = self.text_area.text.split('\n')
                if cursor_row < len(lines):
                    current_line = lines[cursor_row]
                    
                    # For JSON, we need to add the closing quote
                    # Check if we're in JSON mode by looking for quote before partial_key
                    is_json = self.syntax == "json"
                    
                    if is_json:
                        # Replace with suggestion and add closing quote
                        new_line = (
                            current_line[:key_start_col] + 
                            suggestion + 
                            '"' +  # Add closing quote for JSON
                            current_line[cursor_col:]
                        )
                    else:
                        # YAML - no quotes needed
                        new_line = (
                            current_line[:key_start_col] + 
                            suggestion + 
                            current_line[cursor_col:]
                        )
                    
                    lines[cursor_row] = new_line
                    
                    # Update text
                    self.text_area.text = '\n'.join(lines)
                    
                    # Move cursor to end of inserted suggestion (after closing quote for JSON)
                    if is_json:
                        new_col = key_start_col + len(suggestion) + 1  # +1 for closing quote
                    else:
                        new_col = key_start_col + len(suggestion)
                    self.text_area.move_cursor((cursor_row, new_col))
            
            # Hide popup
            self.autocomplete_popup.hide_popup()

    def on_key(self, event):
        """
        Handle key events for autocomplete navigation.
        
        When the autocomplete popup is visible, this method intercepts
        arrow key and tab/escape presses to provide keyboard navigation
        for the suggestion list.
        """
        # Check if autocomplete is visible
        if self.autocomplete_popup.styles.display == "block":
            if event.key == "up":
                self.autocomplete_popup.navigate_up()
                event.prevent_default()
                event.stop()
            elif event.key == "down":
                self.autocomplete_popup.navigate_down()
                event.prevent_default()
                event.stop()
            elif event.key == "tab":
                # Accept the suggestion
                self.action_accept_suggestion()
                event.prevent_default()
                event.stop()
            elif event.key == "escape":
                # Hide the popup
                self.action_hide_autocomplete()
                event.prevent_default()
                event.stop()
