import importlib
import sys
from pathlib import Path
import types
import typing
from typing import Any, Callable, TypeGuard, TypeVar
from pydantic import BaseModel
from pydantic.fields import FieldInfo
import yaml
import json
import inspect
import importlib.util
from pydantic_core import PydanticUndefined


class Parser:
    def __init__(
        self, parse_func: Callable[[str], Any], unparse_func: Callable[[Any], str]
    ):
        self.parse_func = parse_func
        self.unparse_func = unparse_func

    def parse(self, text: str):
        return self.parse_func(text)

    def unparse(self, data) -> str:
        return self.unparse_func(data)


def import_model(model_path: str):
    """
    Import a Pydantic model class from a given path.
    Supports:
      - <location/to/file.py>:<model_class>
      - <location.to.module>:<model_class>
    """
    if ":" not in model_path:
        raise ValueError(
            "Model path must be in the format <module_or_file>:<model_class>"
        )
    location, class_name = model_path.rsplit(":", 1)

    if not class_name.isidentifier():
        raise ValueError(
            f"Invalid class name '{class_name}'. Must be a valid Python identifier."
        )

    if location.endswith(".py"):
        path = Path(location)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path.absolute()}")
    else:
        if not all(part.isidentifier() for part in location.split(".")):
            raise ValueError(
                f"Invalid module path '{location}'. Must be a valid Python module path."
            )

    if location.endswith(".py"):
        spec = importlib.util.spec_from_file_location("user_module", location)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {location}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["user_module"] = module
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(location)

    model_class = getattr(module, class_name, None)
    if model_class is None:
        raise ImportError(f"Model class '{class_name}' not found in '{location}'")

    if not isinstance(model_class, type) or not issubclass(model_class, BaseModel):
        raise TypeError(
            f"{getattr(model_class, '__name__', str(model_class))} is not a subclass of pydantic.BaseModel."
        )
    return model_class


def load_data(file_path: str):
    with open(file_path, "r", encoding="utf-8") as f:
        if file_path.endswith(".yaml") or file_path.endswith(".yml"):
            return yaml.safe_load(f)
        elif file_path.endswith(".json"):
            return json.load(f)
        else:
            raise ValueError("Input file must be .yaml, .yml, or .json")


T = TypeVar("T", bound=type | tuple[type, ...])


def try_issubclass(cls: Any, class_or_tuple: T) -> TypeGuard[T]:
    return isinstance(cls, type) and issubclass(cls, class_or_tuple)


def get_default(annotation: type | types.UnionType) -> typing.Any:
    if isinstance(annotation, types.UnionType):
        args = typing.get_args(annotation)

        # If this is optional, return None
        if types.NoneType in args:
            return None

        for arg in args:
            default = get_default(arg)
            if default is not None:
                return default

        return None

    if try_issubclass(annotation, BaseModel):
        return get_model_default(annotation)
    try:
        return annotation()
    except TypeError:
        return None


def get_field_default(field: FieldInfo):
    val = field.get_default()
    if val not in (inspect._empty, PydanticUndefined):
        return val

    if field.annotation is None:
        return None

    return get_default(field.annotation)


def get_model_default(model_class) -> dict[str, Any]:
    """Generate initial content dict for a new file based on required fields and defaults."""

    def build_dict(model: type[BaseModel]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, field in model.model_fields.items():
            try:
                if try_issubclass(field.annotation, BaseModel):
                    result[name] = build_dict(field.annotation)
                else:
                    result[name] = get_field_default(field)
            except:
                result[name] = None
        return result

    return build_dict(model_class)
