import json
import time
from pathlib import Path
from typing import Literal, Sequence, Union, Optional

import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static, TextArea

from .lib import Parser, get_model_default, render_type_name
from .validate import validate
from .lsp_client import LSPClient
from .lsp_widgets import DiagnosticsPopup, CompletionPopup
from .schema_converter import pydantic_to_json_schema

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
        ("ctrl+space", "show_completions", "Completions"),
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
        
        # LSP support
        self.lsp_client: Optional[LSPClient] = None
        self.diagnostics_popup = DiagnosticsPopup()
        self.completion_popup = CompletionPopup()
        self.lsp_enabled = False
        self.document_version = 1
        self._last_change_time = 0
        self._change_debounce_delay = 0.5  # 500ms debounce

        self.title = "Confantic"
        self.sub_title = f"{self.file_path.name} ({render_type_name(model)})"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield self.text_area
            yield self.validation_panel
        yield self.diagnostics_popup
        yield self.completion_popup
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
        
        # Initialize LSP for JSON files
        if self.syntax == "json":
            self._init_lsp()

    def _init_lsp(self):
        """Initialize the LSP client."""
        try:
            # Convert Pydantic model to JSON schema
            schema = pydantic_to_json_schema(self.model)
            
            # Create file URI
            file_uri = self.file_path.as_uri()
            
            # Start LSP client
            self.lsp_client = LSPClient(schema, file_uri)
            self.lsp_client.start()
            
            # Open the document
            self.lsp_client.did_open(self.text_area.text)
            self.lsp_enabled = True
            
            # Set up periodic diagnostics update
            self.set_interval(0.5, self._update_lsp_diagnostics)
            
        except Exception as e:
            self.notify(
                f"LSP initialization failed: {e}",
                severity="warning",
                timeout=3,
            )

    def _update_lsp_diagnostics(self):
        """Update diagnostics from LSP."""
        if not self.lsp_enabled or not self.lsp_client:
            return
            
        try:
            diagnostics = self.lsp_client.get_diagnostics()
            self.diagnostics_popup.update_diagnostics(diagnostics)
        except Exception:
            # Silently ignore errors
            pass

    def on_text_area_changed(self, event):
        """Handle text area changes."""
        if not self.lsp_enabled or not self.lsp_client:
            return
        
        # Debounce: only send changes after a delay
        self._last_change_time = time.time()
        self.document_version += 1
        
        # Schedule a delayed update
        self.set_timer(
            self._change_debounce_delay,
            self._send_lsp_change,
        )

    def _send_lsp_change(self):
        """Send document changes to LSP after debounce delay."""
        if not self.lsp_enabled or not self.lsp_client:
            return
            
        # Check if enough time has passed since last change
        time_since_change = time.time() - self._last_change_time
        if time_since_change < self._change_debounce_delay:
            return
        
        try:
            self.lsp_client.did_change(
                self.text_area.text,
                self.document_version
            )
        except Exception:
            # Silently ignore errors
            pass

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

    def action_show_completions(self):
        """Show LSP completions at the current cursor position."""
        if not self.lsp_enabled or not self.lsp_client:
            return
        
        # Get cursor position
        cursor = self.text_area.cursor_location
        line, character = cursor
        
        def on_completions(items):
            self.completion_popup.update_completions(items)
            if items:
                # Auto-hide after a few seconds
                self.set_timer(5.0, self.completion_popup.hide)
        
        try:
            self.lsp_client.completion(
                self.text_area.text,
                line,
                character,
                on_completions
            )
        except Exception:
            # Silently ignore errors
            pass

    def on_unmount(self):
        """Clean up LSP client when app closes."""
        if self.lsp_client:
            try:
                self.lsp_client.stop()
            except Exception:
                pass
