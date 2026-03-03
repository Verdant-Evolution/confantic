"""Test LSP integration components."""
import pytest
import json
import time
from pathlib import Path
from pydantic import BaseModel

from confantic.schema_converter import pydantic_to_json_schema
from confantic.lsp_client import LSPClient


class SimpleModel(BaseModel):
    """A simple model for testing."""
    name: str
    value: int
    enabled: bool = True


def test_pydantic_to_json_schema():
    """Test conversion of Pydantic model to JSON schema."""
    schema = pydantic_to_json_schema(SimpleModel)
    
    assert "properties" in schema
    assert "name" in schema["properties"]
    assert "value" in schema["properties"]
    assert "enabled" in schema["properties"]
    assert schema["properties"]["name"]["type"] == "string"
    assert schema["properties"]["value"]["type"] == "integer"
    assert schema["properties"]["enabled"]["type"] == "boolean"
    assert "required" in schema
    assert "name" in schema["required"]
    assert "value" in schema["required"]


def test_lsp_client_initialization():
    """Test that LSP client can be initialized."""
    schema = pydantic_to_json_schema(SimpleModel)
    file_uri = "file:///tmp/test.json"
    
    client = LSPClient(schema, file_uri)
    assert client.schema == schema
    assert client.file_uri == file_uri
    assert client.process is None


def test_lsp_client_start_stop():
    """Test that LSP client can be started and stopped."""
    schema = pydantic_to_json_schema(SimpleModel)
    file_uri = "file:///tmp/test.json"
    
    client = LSPClient(schema, file_uri)
    
    try:
        client.start()
        assert client.process is not None
        assert client._running
        
        # Give it a moment to initialize
        time.sleep(1)
        
        # Open a document
        client.did_open('{"name": "test", "value": 42}')
        
        # Give it time to process
        time.sleep(1)
        
    finally:
        client.stop()
        time.sleep(0.5)
        assert not client._running


def test_lsp_client_diagnostics():
    """Test that LSP client receives diagnostics for invalid JSON."""
    schema = pydantic_to_json_schema(SimpleModel)
    file_uri = "file:///tmp/test_invalid.json"
    
    client = LSPClient(schema, file_uri)
    
    try:
        client.start()
        time.sleep(1)
        
        # Open a document with missing required field
        invalid_json = '{"name": "test"}'
        client.did_open(invalid_json)
        
        # Give LSP time to validate and send diagnostics
        time.sleep(2)
        
        diagnostics = client.get_diagnostics()
        # We expect at least one diagnostic for the missing field
        assert len(diagnostics) > 0, "Expected diagnostics for missing required field"
        
        # Check that we got a diagnostic about the value field
        has_value_error = any(
            "value" in diag.get("message", "").lower()
            for diag in diagnostics
        )
        assert has_value_error, "Expected diagnostic about missing 'value' field"
        
    finally:
        client.stop()
        time.sleep(0.5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

