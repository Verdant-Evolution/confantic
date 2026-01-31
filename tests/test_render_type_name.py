from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, TypeAdapter

from confantic.lib import render_type_name


def test_render_type_name_base_model():

    class MyModel(BaseModel):
        field: int

    assert render_type_name(MyModel) == "MyModel"
    assert render_type_name(TypeAdapter(MyModel)) == "MyModel"


def test_render_type_name_builtin_types():
    assert render_type_name(int) == "int"
    assert render_type_name(str) == "str"
    assert render_type_name(float) == "float"
    assert render_type_name(bool) == "bool"
    assert render_type_name(list) == "list"
    assert render_type_name(dict) == "dict"
    assert render_type_name(type(None)) == "None"


def test_render_type_name_typing_types():

    assert render_type_name(List[int]) == "list[int]"
    assert render_type_name(Dict[str, int]) == "dict[str, int]"
    assert render_type_name(Optional[int]) == "int?"
    assert render_type_name(Union[int, str]) == "int | str"
    assert render_type_name(Tuple[int, str]) == "(int, str)"
    assert render_type_name(Any) == "Any"


def test_render_type_name_nested_models():
    class Inner(BaseModel):
        foo: int

    class Outer(BaseModel):
        bar: Inner

    assert render_type_name(Inner) == "Inner"
    assert render_type_name(Outer) == "Outer"
    assert render_type_name(TypeAdapter(Outer)) == "Outer"


def test_render_type_name_type_adapter_with_typing():

    class MyModel(BaseModel):
        field: int

    adapter = TypeAdapter(List[MyModel])
    assert render_type_name(adapter) == "list[MyModel]"


def test_render_type_name_custom_class():
    class Custom:
        pass

    assert render_type_name(Custom) == "Custom"


def test_render_type_name_type_adapter_with_union():

    class A(BaseModel):
        a: int

    class B(BaseModel):
        b: str

    adapter = TypeAdapter(Union[A, B])
    assert render_type_name(adapter) == "A | B"
