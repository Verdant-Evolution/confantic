import importlib
import importlib.util
import inspect
import json
import sys
import types
import typing
from pathlib import Path
from typing import Any, Callable, TypeGuard, TypeVar

import yaml
from pydantic import BaseModel, TypeAdapter
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from typing_inspect import (
    get_bound,
    get_constraints,
    is_generic_type,
    is_literal_type,
    is_optional_type,
    is_tuple_type,
    is_typevar,
    is_union_type,
)
from typing_inspection.introspection import get_literal_values


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


def render_type_name(typ: Any) -> str:
    if try_issubclass(typ, BaseModel):
        return typ.__name__

    if isinstance(typ, TypeAdapter):
        return render_type_name(typ._type)

    if is_literal_type(typ):
        return ", ".join(repr(v) for v in get_literal_values(typ))

    if is_tuple_type(typ):
        return f"({', '.join(render_type_name(a) for a in typing.get_args(typ))})"

    if is_optional_type(typ):
        if args := typing.get_args(typ):
            non_none = args[0] if args[1] is type(None) else args[1]
            return f"{render_type_name(non_none)}?"

    if is_union_type(typ):
        return " | ".join(render_type_name(a) for a in typing.get_args(typ))

    if is_generic_type(typ):
        args = typing.get_args(typ)
        origin = typing.get_origin(typ)
        if args:
            return f"{render_type_name(origin)}[{', '.join(render_type_name(a) for a in args)}]"
        else:
            return render_type_name(origin)
    if try_issubclass(typ, types.NoneType):
        return "None"

    origin = typing.get_origin(typ)
    if origin is not None:
        return render_type_name(origin)

    if hasattr(typ, "__name__"):
        return typ.__name__

    return "Unknown"


T = TypeVar("T", bound=type | tuple[type, ...])


def try_issubclass(cls: Any, class_or_tuple: T) -> TypeGuard[T]:
    return isinstance(cls, type) and issubclass(cls, class_or_tuple)


def get_default(annotation: Any) -> Any:
    """
    Attempts to get a default value for a given type annotation.
    Returns None if no default can be determined.
    """
    if try_issubclass(annotation, BaseModel) or isinstance(annotation, TypeAdapter):
        return get_model_default(annotation)

    if is_literal_type(annotation):
        for v in get_literal_values(annotation):
            return v
        return None

    if is_optional_type(annotation):
        return None

    if is_typevar(annotation):
        for constraint in get_constraints(annotation):
            default = get_default(constraint)
            if default is not None:
                return default

        return get_default(get_bound(annotation))

    if is_union_type(annotation):
        for arg in typing.get_args(annotation):
            default = get_default(arg)
            if default is not None:
                return default

        return None

    try:
        return annotation()
    except TypeError:
        origin = typing.get_origin(annotation)
        if origin is not None:
            return get_default(origin)
        return None


def get_field_default(field: FieldInfo):
    """
    Attempts to get the default value for a Pydantic field.
    Returns None if no default is set or can be determined from the annotation.
    """
    val = field.get_default()
    if val not in (inspect._empty, PydanticUndefined):
        return val

    if field.annotation is None:
        return None

    return get_default(field.annotation)


def get_model_default(model_class: type[BaseModel] | TypeAdapter) -> dict[str, Any]:
    """Generate initial content dict for a new file based on required fields and defaults."""

    def build_dict(model: type[BaseModel] | TypeAdapter) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if isinstance(model, TypeAdapter):
            return get_default(model._type)

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
