import json
from pathlib import Path
from typing import Literal, Sequence

import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, Static, TextArea

from .lib import Parser, get_model_default, render_type_name
from .validate import validate

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
    ]

    def __init__(
        self,
        model: type[BaseModel] | TypeAdapter,
        file_path: Path | str,
        force_format: ParseFormat | None = None,
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

        self.title = "Confantic"
        self.sub_title = f"{self.file_path.name} ({render_type_name(model)})"

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield self.text_area
            yield self.validation_panel
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
            loc: Sequence[int | str] = err.get("loc", [])
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
