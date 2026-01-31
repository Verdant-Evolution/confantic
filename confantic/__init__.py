from pydantic import BaseModel
from pathlib import Path


def edit(cls: type[BaseModel], filepath: str | Path):
    """
    Launch the Confantic editor for the given Pydantic model and file.

    Args:
        cls (type[BaseModel]): The Pydantic model class to use for validation.
        filepath (str | Path): The path to the YAML/JSON file to edit.

    """
    from .editor import Editor

    if isinstance(filepath, str):
        filepath = Path(filepath)

    Editor(cls, filepath).run()
