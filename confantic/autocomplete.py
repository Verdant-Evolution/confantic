"""Autocomplete functionality for JSON/YAML config editing using tree-sitter."""

import tree_sitter
import tree_sitter_json
import tree_sitter_yaml
from typing import Optional, Union

from pydantic import BaseModel, TypeAdapter
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import OptionList
from textual.widget import Widget
from textual.geometry import Offset


# Initialize tree-sitter parsers
_JSON_LANGUAGE = tree_sitter.Language(tree_sitter_json.language())
_YAML_LANGUAGE = tree_sitter.Language(tree_sitter_yaml.language())

_JSON_PARSER = tree_sitter.Parser(_JSON_LANGUAGE)
_YAML_PARSER = tree_sitter.Parser(_YAML_LANGUAGE)


class AutocompletePopup(Container):
    """A popup widget that displays autocomplete suggestions."""

    DEFAULT_CSS = """
    AutocompletePopup {
        layer: overlay;
        width: auto;
        height: auto;
        max-height: 10;
        background: $surface;
        border: solid $primary;
        display: none;
    }
    
    AutocompletePopup > OptionList {
        width: 30;
        height: auto;
        max-height: 10;
        background: $surface;
        border: none;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.option_list = OptionList()

    def compose(self) -> ComposeResult:
        yield self.option_list

    def show_suggestions(self, suggestions: list[str], position: Offset):
        """Show the popup with suggestions at the given position."""
        if not suggestions:
            self.hide_popup()
            return

        self.option_list.clear_options()
        for suggestion in suggestions:
            self.option_list.add_option(suggestion)
        
        # Position the popup
        self.styles.offset = (position.x, position.y)
        self.styles.display = "block"
        
        # Highlight first option
        if len(suggestions) > 0:
            self.option_list.highlighted = 0

    def hide_popup(self):
        """Hide the popup."""
        self.styles.display = "none"
        self.option_list.clear_options()

    def get_selected_suggestion(self) -> Optional[str]:
        """Get the currently highlighted suggestion."""
        if self.option_list.highlighted is not None:
            option = self.option_list.get_option_at_index(self.option_list.highlighted)
            if option is not None:
                return str(option.prompt)
        return None

    def navigate_up(self):
        """Navigate to the previous suggestion."""
        if self.option_list.option_count > 0:
            self.option_list.action_cursor_up()

    def navigate_down(self):
        """Navigate to the next suggestion."""
        if self.option_list.option_count > 0:
            self.option_list.action_cursor_down()


# Tree-sitter helper functions

def _find_deepest_node_at_position(node: tree_sitter.Node, row: int, col: int) -> Optional[tree_sitter.Node]:
    """
    Find the deepest node in the tree at the given position.
    
    Args:
        node: The node to start searching from
        row: The row number (0-indexed)
        col: The column number (0-indexed)
        
    Returns:
        The deepest node at the position, or None if not found
    """
    # Check if position is within this node's range
    start_row, start_col = node.start_point
    end_row, end_col = node.end_point
    
    # Check if row is in range
    if row < start_row or row > end_row:
        return None
    
    # Check column boundaries
    if row == start_row and col < start_col:
        return None
    if row == end_row and col > end_col:
        return None
    
    # Try to find a deeper child node at this position
    for child in node.children:
        result = _find_deepest_node_at_position(child, row, col)
        if result:
            return result
    
    # No children match, return this node
    return node


def _is_typing_json_key(node: tree_sitter.Node) -> tuple[bool, Optional[str]]:
    """
    Check if a node represents typing a JSON key.
    
    Returns:
        Tuple of (is_key, partial_text)
    """
    if not node:
        return False, None
    
    # If we're at a string_content node, check if it's a key
    if node.type == 'string_content':
        parent = node.parent
        
        # Case 1: In ERROR (incomplete JSON) - check for quote before
        if parent and parent.type == 'ERROR':
            for i, child in enumerate(parent.children):
                if child == node and i > 0:
                    if parent.children[i-1].type == '"':
                        return True, node.text.decode('utf-8')
        
        # Case 2: In a complete pair - check if we're the key
        if parent and parent.type == 'string':
            grandparent = parent.parent
            if grandparent and grandparent.type == 'pair':
                # First child is the key
                if grandparent.children and grandparent.children[0] == parent:
                    return True, node.text.decode('utf-8')
    
    return False, None


def _is_typing_yaml_key(node: tree_sitter.Node) -> tuple[bool, Optional[str]]:
    """
    Check if a node represents typing a YAML key.
    
    Returns:
        Tuple of (is_key, partial_text)
    """
    if not node:
        return False, None
    
    # In YAML, we need to walk up the tree to find if we're in a key position
    # The hierarchy is typically: string_scalar -> plain_scalar -> flow_node -> block_mapping_pair
    current = node
    for _ in range(4):  # Walk up max 4 levels
        if not current:
            break
        
        # Check if we're at a mapping pair level
        if current.type in ['block_mapping_pair', 'flow_pair']:
            # Check if our original node is part of the first child (the key)
            if current.children and len(current.children) > 0:
                key_node = current.children[0]
                # Check if our node is within the key node's range
                if (node.start_point[0] >= key_node.start_point[0] and 
                    node.end_point[0] <= key_node.end_point[0]):
                    # We're in the key!
                    text = key_node.text.decode('utf-8')
                    # Remove quotes if present
                    if text.startswith('"') or text.startswith("'"):
                        text = text[1:-1] if len(text) > 1 else text[1:]
                    return True, text
        
        current = current.parent
    
    return False, None


def _get_containing_object_node(node: tree_sitter.Node, is_json: bool) -> Optional[tree_sitter.Node]:
    """
    Find the containing object/map node for the given node.
    
    Args:
        node: The starting node
        is_json: Whether we're parsing JSON or YAML
        
    Returns:
        The containing object node or None
    """
    current = node
    target_types = ['object', 'ERROR'] if is_json else ['block_mapping', 'flow_mapping', 'ERROR']
    
    while current:
        if current.type in target_types:
            return current
        current = current.parent
    
    return None


def _extract_keys_from_object(object_node: tree_sitter.Node, is_json: bool) -> list[str]:
    """
    Extract existing keys from an object/map node.
    
    Args:
        object_node: The object or mapping node
        is_json: Whether we're parsing JSON or YAML
        
    Returns:
        List of existing key names
    """
    keys = []
    
    if is_json:
        # JSON: look for pair nodes (they could be direct children or nested)
        def extract_pairs(node, depth=0):
            """Recursively extract pair nodes at the same nesting level."""
            for child in node.children:
                if child.type == 'pair':
                    # Extract the key from the first child
                    key_node = child.children[0] if child.children else None
                    if key_node and key_node.type == 'string':
                        # Extract string_content
                        for sc in key_node.children:
                            if sc.type == 'string_content':
                                keys.append(sc.text.decode('utf-8'))
                                break
                elif child.type in ['object', 'ERROR'] and depth == 0:
                    # Don't recurse into nested objects
                    continue
        
        extract_pairs(object_node)
    else:
        # YAML: look for block_mapping_pair or flow_pair nodes
        for child in object_node.children:
            if child.type in ['block_mapping_pair', 'flow_pair']:
                # First child is the key
                key_node = child.children[0] if child.children else None
                if key_node:
                    text = key_node.text.decode('utf-8')
                    # Remove quotes if present
                    if text.startswith('"') or text.startswith("'"):
                        text = text[1:-1] if len(text) > 1 else text[1:]
                    keys.append(text)
    
    return keys


def _get_object_path(node: tree_sitter.Node, is_json: bool) -> list[str]:
    """
    Get the path from root to the containing object.
    
    Args:
        node: The starting node
        is_json: Whether we're parsing JSON or YAML
        
    Returns:
        List of field names representing the path
    """
    path = []
    current = node
    
    # Walk up the tree, collecting keys as we go
    while current:
        parent = current.parent
        if not parent:
            break
        
        # Check if current is an object/mapping value
        if is_json:
            if parent.type == 'pair':
                # Get the key for this pair
                key_node = parent.children[0] if parent.children else None
                if key_node and key_node.type == 'string':
                    for sc in key_node.children:
                        if sc.type == 'string_content':
                            path.insert(0, sc.text.decode('utf-8'))
                            break
                # Move up to the object containing this pair
                current = parent.parent
                continue
        else:
            if parent.type in ['block_mapping_pair', 'flow_pair']:
                # Get the key for this pair
                key_node = parent.children[0] if parent.children else None
                if key_node:
                    text = key_node.text.decode('utf-8')
                    if text.startswith('"') or text.startswith("'"):
                        text = text[1:-1] if len(text) > 1 else text[1:]
                    path.insert(0, text)
                # Move up to the mapping containing this pair
                current = parent.parent
                continue
        
        current = parent
    
    return path


def get_field_names(model: Union[type[BaseModel], TypeAdapter]) -> list[str]:
    """Extract all field names from a Pydantic model."""
    if isinstance(model, TypeAdapter):
        # For TypeAdapter, we can't extract field names easily
        return []
    
    if isinstance(model, type) and issubclass(model, BaseModel):
        return list(model.model_fields.keys())
    
    return []


def get_current_context(text: str, cursor_row: int, cursor_col: int, is_json: bool = True) -> tuple[Optional[str], int]:
    """
    Determine the current editing context at the cursor position using tree-sitter.
    
    Args:
        text: The full text content
        cursor_row: The cursor row (0-indexed)
        cursor_col: The cursor column (0-indexed)
        is_json: Whether parsing JSON (True) or YAML (False)
        
    Returns:
        A tuple of (partial_key, key_start_col) where:
        - partial_key is the partially typed key name, or None if not typing a key
        - key_start_col is the column where the key started
    """
    # Parse the text
    text_bytes = text.encode('utf-8')
    parser = _JSON_PARSER if is_json else _YAML_PARSER
    tree = parser.parse(text_bytes)
    
    # Find the node at the cursor position
    node = _find_deepest_node_at_position(tree.root_node, cursor_row, cursor_col)
    if not node:
        return None, 0
    
    # Check if we're typing a key
    if is_json:
        is_key, partial_text = _is_typing_json_key(node)
    else:
        is_key, partial_text = _is_typing_yaml_key(node)
    
    if is_key and partial_text:
        # Calculate the start column
        # For JSON, the key starts after the quote
        if is_json:
            key_start_col = node.start_point[1]
        else:
            key_start_col = node.start_point[1]
        
        return partial_text, key_start_col
    
    return None, 0


def filter_suggestions(field_names: list[str], partial_key: str) -> list[str]:
    """Filter field names based on the partial key typed by the user."""
    if not partial_key:
        return field_names
    
    # Case-insensitive prefix matching
    partial_lower = partial_key.lower()
    return [name for name in field_names if name.lower().startswith(partial_lower)]


def get_existing_keys_in_current_object(text: str, cursor_row: int, cursor_col: int, is_json: bool = True) -> list[str]:
    """
    Extract keys that already exist in the current JSON/YAML object using tree-sitter.
    
    Args:
        text: The full text content
        cursor_row: The cursor row (0-indexed)
        cursor_col: The cursor column (0-indexed)
        is_json: Whether parsing JSON (True) or YAML (False)
        
    Returns:
        A list of key names that are already present in the current object scope
    """
    # Parse the text
    text_bytes = text.encode('utf-8')
    parser = _JSON_PARSER if is_json else _YAML_PARSER
    tree = parser.parse(text_bytes)
    
    # Find the node at the cursor position
    node = _find_deepest_node_at_position(tree.root_node, cursor_row, cursor_col)
    if not node:
        return []
    
    # Find the containing object/mapping
    object_node = _get_containing_object_node(node, is_json)
    if not object_node:
        return []
    
    # Extract keys from this object
    return _extract_keys_from_object(object_node, is_json)


def get_nested_model_at_path(model: Union[type[BaseModel], TypeAdapter], path: list[str]) -> Optional[Union[type[BaseModel], TypeAdapter]]:
    """
    Get the nested model at the given path.
    
    Args:
        model: The root Pydantic model
        path: List of field names representing the path to the nested object
        
    Returns:
        The nested model if found, otherwise None
    """
    if isinstance(model, TypeAdapter) or not path:
        return model
    
    if not (isinstance(model, type) and issubclass(model, BaseModel)):
        return None
    
    current_model = model
    for field_name in path:
        if not hasattr(current_model, 'model_fields'):
            return None
            
        if field_name not in current_model.model_fields:
            return None
        
        field_info = current_model.model_fields[field_name]
        field_type = field_info.annotation
        
        # Check if it's a BaseModel
        if isinstance(field_type, type) and issubclass(field_type, BaseModel):
            current_model = field_type
        else:
            # Not a nested model
            return None
    
    return current_model


def get_current_object_path(text: str, cursor_row: int, cursor_col: int, is_json: bool = True) -> list[str]:
    """
    Determine the path to the current object being edited using tree-sitter.
    
    Args:
        text: The full text content
        cursor_row: The cursor row (0-indexed)
        cursor_col: The cursor column (0-indexed)
        is_json: Whether parsing JSON (True) or YAML (False)
        
    Returns:
        A list of field names representing the nesting path,
        e.g., [] for root, ['address'] for inside an address object.
    """
    # Parse the text
    text_bytes = text.encode('utf-8')
    parser = _JSON_PARSER if is_json else _YAML_PARSER
    tree = parser.parse(text_bytes)
    
    # Find the node at the cursor position
    node = _find_deepest_node_at_position(tree.root_node, cursor_row, cursor_col)
    if not node:
        return []
    
    # Get the path by walking up the tree
    return _get_object_path(node, is_json)
