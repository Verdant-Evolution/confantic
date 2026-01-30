from pathlib import Path
import textwrap
import sys
import types
import pytest
import pydantic
from confantic.lib import import_model


def test_import_model_from_module(monkeypatch: pytest.MonkeyPatch) -> None:
    # Create a dummy module in sys.modules with a real Pydantic model
    module_name = "dummy_module"
    class_name = "DummyModel"

    class DummyModel(pydantic.BaseModel):
        x: int = 1

    dummy_module = types.ModuleType(module_name)
    setattr(dummy_module, class_name, DummyModel)
    monkeypatch.setitem(sys.modules, module_name, dummy_module)

    model = import_model(f"{module_name}:{class_name}")
    assert model is DummyModel


def test_import_model_from_file(tmp_path: Path) -> None:
    # Write a temporary Python file with a real Pydantic model class
    file_content = textwrap.dedent(
        """
        import pydantic
        class DummyModel(pydantic.BaseModel):
            x: int = 1
        """
    )
    file_path = tmp_path / "model_file.py"
    file_path.write_text(file_content)

    model = import_model(f"{file_path}:{'DummyModel'}")
    assert model.__name__ == "DummyModel"


def test_import_model_invalid_class():
    with pytest.raises(ValueError):
        import_model("module:123InvalidClass")


def test_import_model_invalid_module():
    with pytest.raises(ValueError):
        import_model("invalid-module!:Model")


def test_import_model_file_not_found():
    with pytest.raises(FileNotFoundError):
        import_model("not_a_real_file.py:Model")


def test_import_model_class_not_found(tmp_path: Path):
    file_content = """class NotTheModel: pass"""
    file_path = tmp_path / "model_file.py"
    file_path.write_text(file_content)
    with pytest.raises(ImportError):
        import_model(f"{file_path}:MissingModel")


def test_import_model_not_pydantic_class(tmp_path: Path):
    # Write a temporary Python file with a non-pydantic class
    file_content = """
class NotPydantic:
    pass
"""
    file_path = tmp_path / "not_pydantic.py"
    file_path.write_text(file_content)
    import sys

    sys.path.insert(0, str(tmp_path))
    try:
        import pytest

        with pytest.raises(TypeError):
            import_model(f"{file_path}:NotPydantic")
    finally:
        sys.path.pop(0)

    # Test with a module
    import types

    module_name = "not_pydantic_mod"
    NotPydantic = type("NotPydantic", (), {})
    dummy_module = types.ModuleType(module_name)
    setattr(dummy_module, "NotPydantic", NotPydantic)
    sys.modules[module_name] = dummy_module
    import pytest

    with pytest.raises(TypeError):
        import_model(f"{module_name}:NotPydantic")
