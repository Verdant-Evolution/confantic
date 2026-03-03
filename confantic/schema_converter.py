"""Utilities for converting Pydantic models to JSON Schema."""
from typing import Union
from pydantic import BaseModel, TypeAdapter


def pydantic_to_json_schema(model: Union[type[BaseModel], TypeAdapter]) -> dict:
    """
    Convert a Pydantic model to JSON Schema.
    
    Args:
        model: Pydantic BaseModel class or TypeAdapter
        
    Returns:
        JSON Schema as a dictionary
    """
    if isinstance(model, TypeAdapter):
        # For TypeAdapter, use the model_json_schema method
        return model.json_schema()
    else:
        # For BaseModel, use model_json_schema
        return model.model_json_schema()
