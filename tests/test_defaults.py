from confantic.lib import get_model_default, get_default
from pydantic import BaseModel


def test_primitives():
    assert get_default(str) == ""
    assert get_default(int) == 0
    assert get_default(float) == 0.0
    assert get_default(bool) is False
    assert get_default(list) == []
    assert get_default(dict) == {}
    assert get_default(set) == set()
    assert get_default(tuple) == ()
    assert get_default(str | int) == ""


def test_primitive_model():
    class PrimitiveModel(BaseModel):
        string: str
        number: int
        flag: bool
        string_or_int: str | int
        list_field: list[str]
        dict_field: dict[str, int]
        set_field: set[float] = set()
        tuple_field: tuple = ()

    assert get_model_default(PrimitiveModel) == {
        "string": "",
        "number": 0,
        "flag": False,
        "string_or_int": "",
        "list_field": [],
        "dict_field": {},
        "set_field": set(),
        "tuple_field": (),
    }


def test_nested_model():
    class InnerModel(BaseModel):
        inner_string: str
        inner_number: int = 42

    class OuterModel(BaseModel):
        outer_string: str
        inner_model: InnerModel

    assert get_model_default(OuterModel) == {
        "outer_string": "",
        "inner_model": {
            "inner_string": "",
            "inner_number": 42,
        },
    }


def test_optional_fields():
    class OptionalModel(BaseModel):
        required_field: str
        optional_field: str | None
        optional_with_default: int | None = 10

    assert get_model_default(OptionalModel) == {
        "required_field": "",
        "optional_field": None,
        "optional_with_default": 10,
    }
