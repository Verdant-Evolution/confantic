"""Autocomplete functionality for JSON/YAML config editing."""

from typing import Optional, Union, Literal

from pydantic import BaseModel, TypeAdapter
from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import OptionList
from textual.widget import Widget
from textual.geometry import Offset

from .tree_sitter_utils import (
    parse_document,
    find_node_at_position,
    find_parent_object_node,
    extract_object_keys,
    get_object_path_to_node,
    is_in_key_position,
    get_node_text,
)


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


def get_field_names(model: Union[type[BaseModel], TypeAdapter]) -> list[str]:
    """Extract all field names from a Pydantic model."""
    if isinstance(model, TypeAdapter):
        # For TypeAdapter, we can't extract field names easily
        return []
    
    if isinstance(model, type) and issubclass(model, BaseModel):
        return list(model.model_fields.keys())
    
    return []


def get_current_context(text: str, cursor_row: int, cursor_col: int, format_type: Literal["json", "yaml"]) -> tuple[Optional[str], int]:
    """
    Determine the current editing context at the cursor position using tree-sitter.
    
    Args:
        text: The document text
        cursor_row: Zero-indexed row number
        cursor_col: Zero-indexed column number  
        format_type: Either "json" or "yaml"
        
    Returns:
        A tuple of (partial_key, key_start_col) where:
        - partial_key is the partially typed key name, or None if not typing a key
        - key_start_col is the column where the key started
    """
    if not text.strip():
        return None, 0
    
    try:
        tree = parse_document(text, format_type)
        source = bytes(text, 'utf8')
        
        # Find the node at cursor position
        node = find_node_at_position(tree.root_node, cursor_row, cursor_col)
        
        if not node:
            return None, 0
        
        # Check if we're in a key position
        if format_type == "json":
            # For JSON, check if we're typing inside a string that's a key
            # Handle both complete and incomplete (ERROR) states
            current = node
            
            # If we're in string_content, check if it's part of a key
            if current.type == "string_content":
                # Extract the text
                partial_text = source[current.start_byte:current.end_byte].decode('utf8')
                
                # Look for the opening quote before this content
                # Walk up to find context
                parent = current.parent
                
                # Check if parent is ERROR (incomplete string) or string (complete)
                if parent and (parent.type == "ERROR" or parent.type == "string"):
                    # For incomplete strings (ERROR nodes), we need to check the context
                    # Is there an opening quote before us?
                    lines = text.split('\n')
                    if cursor_row < len(lines):
                        current_line = lines[cursor_row]
                        before_content = current_line[:current.start_point[1]]
                        
                        # Check if there's a quote before the content
                        if '"' in before_content:
                            # Find the last quote position
                            quote_pos = before_content.rfind('"')
                            # Check what comes before the quote
                            before_quote = before_content[:quote_pos].strip()
                            
                            # If it's after { or ,, we're in a key position
                            if before_quote.endswith('{') or before_quote.endswith(',') or before_quote == '':
                                # This is a key position
                                key_start_col = quote_pos + 1
                                if len(partial_text) > 0:
                                    return partial_text, key_start_col
                                else:
                                    return None, 0
            
            # Check for complete string nodes
            while current and current.type not in ["string", "pair", "object", "document", "ERROR"]:
                current = current.parent
            
            if current and current.type == "string":
                # Check if this string is a key (first child of a pair)
                string_node = current
                parent = string_node.parent
                
                if parent and parent.type == "pair":
                    # Check if we're the first child (the key)
                    if parent.children and parent.children[0] == string_node:
                        # We're in the key string
                        # Find the string_content node
                        for child in string_node.children:
                            if child.type == "string_content":
                                # Extract the partial key text
                                partial_text = source[child.start_byte:child.end_byte].decode('utf8')
                                # Calculate where the key starts (after opening quote)
                                key_start_col = string_node.start_point[1] + 1
                                
                                # Only trigger if there's at least one character
                                if len(partial_text) > 0:
                                    return partial_text, key_start_col
                                else:
                                    return None, 0
                        
                        # If no string_content, might be empty string
                        return None, 0
                        
        elif format_type == "yaml":
            # For YAML, check if we're in a key position
            current = node
            
            # Handle string_scalar (complete keys)
            if current.type == "string_scalar":
                # Check if this is a key in a mapping pair
                # Walk up through plain_scalar and flow_node
                parent = current.parent
                while parent and parent.type in ["plain_scalar", "flow_node"]:
                    parent = parent.parent
                
                if parent and parent.type == "block_mapping_pair":
                    # Check if we're the first flow_node (the key) or second (the value)
                    # Count flow_node children before us
                    flow_node_index = 0
                    for child in parent.children:
                        if child.type == "flow_node":
                            # Check if current node is inside this flow_node
                            # by walking up from current
                            temp = current
                            while temp and temp != parent:
                                if temp == child:
                                    # We found ourselves
                                    break
                                temp = temp.parent
                            if temp == child:
                                # We're in this flow_node
                                break
                            flow_node_index += 1
                    
                    # If flow_node_index is 0, we're the key; if 1+, we're a value
                    if flow_node_index == 0:
                        # Extract the text
                        partial_text = source[current.start_byte:current.end_byte].decode('utf8')
                        key_start_col = current.start_point[1]
                        
                        if len(partial_text) > 0:
                            return partial_text, key_start_col
            
            # For incomplete YAML (might be in ERROR or text node)
            # Check if we're at start of line typing a word
            if current.type in ["string_scalar", "ERROR"] or "scalar" in current.type:
                lines = text.split('\n')
                if cursor_row < len(lines):
                    current_line = lines[cursor_row]
                    before_cursor = current_line[:cursor_col]
                    
                    # Check if we're at start of line or after whitespace
                    # and not after a colon (value position)
                    if ':' not in before_cursor:
                        stripped = before_cursor.strip()
                        if stripped:
                            # Find where the word starts
                            for i in range(len(before_cursor) - 1, -1, -1):
                                if not (before_cursor[i].isalnum() or before_cursor[i] == '_'):
                                    key_start_col = i + 1
                                    partial_text = before_cursor[key_start_col:]
                                    if partial_text:
                                        return partial_text, key_start_col
                            # Word starts at beginning of stripped part
                            key_start_col = len(before_cursor) - len(stripped)
                            return stripped, key_start_col
        
    except Exception as e:
        # If tree-sitter parsing fails, fall back to returning None
        pass
    
    return None, 0


def filter_suggestions(field_names: list[str], partial_key: str) -> list[str]:
    """Filter field names based on the partial key typed by the user."""
    if not partial_key:
        return field_names
    
    # Case-insensitive prefix matching
    partial_lower = partial_key.lower()
    return [name for name in field_names if name.lower().startswith(partial_lower)]


def get_existing_keys_in_current_object(text: str, cursor_row: int, cursor_col: int, format_type: Literal["json", "yaml"]) -> list[str]:
    """
    Extract keys that already exist in the current JSON/YAML object using tree-sitter.
    
    Args:
        text: The document text
        cursor_row: Zero-indexed row number
        cursor_col: Zero-indexed column number
        format_type: Either "json" or "yaml"
        
    Returns:
        A list of key names that are already present in the current object scope
    """
    if not text.strip():
        return []
    
    try:
        tree = parse_document(text, format_type)
        source = bytes(text, 'utf8')
        
        # Find the node at cursor position
        node = find_node_at_position(tree.root_node, cursor_row, cursor_col)
        
        # If no node found, try using the root node (for incomplete trees)
        if not node:
            node = tree.root_node
        
        # Find the parent object/mapping node
        parent_obj = find_parent_object_node(node, format_type)
        
        # If still no parent found, check if root is an ERROR node with object-like structure
        if not parent_obj and tree.root_node.type == "ERROR":
            parent_obj = tree.root_node
        
        if not parent_obj:
            return []
        
        # Extract all keys from this object
        keys = extract_object_keys(parent_obj, source, format_type)
        
        return keys
        
    except Exception as e:
        # If parsing fails, return empty list
        return []


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


def get_current_object_path(text: str, cursor_row: int, cursor_col: int, format_type: Literal["json", "yaml"]) -> list[str]:
    """
    Determine the path to the current object being edited using tree-sitter.
    
    For incomplete trees, we need to manually count brace nesting.
    
    Args:
        text: The document text
        cursor_row: Zero-indexed row number
        cursor_col: Zero-indexed column number
        format_type: Either "json" or "yaml"
        
    Returns:
        A list of field names representing the nesting path,
        e.g., [] for root, ['address'] for inside an address object.
    """
    if not text.strip():
        return []
    
    try:
        tree = parse_document(text, format_type)
        source = bytes(text, 'utf8')
        
        if format_type == "json":
            # For JSON, manually walk through the structure looking for nested braces
            # Count brace depth and find keys before each opening brace
            path = []
            
            # Get all children of root (which might be ERROR for incomplete JSON)
            root = tree.root_node
            children = root.children if root.type in ["document", "ERROR"] else [root]
            
            # Find all opening braces and their associated keys
            # Structure: ... "key" : { ...
            brace_positions = []
            for i, child in enumerate(children):
                if child.type == "{":
                    # Look for key before this brace
                    if i >= 2:
                        colon = children[i - 1]
                        key_node = children[i - 2]
                        
                        if colon.type == ":" and key_node.type == "string":
                            # Extract key text
                            for grandchild in key_node.children:
                                if grandchild.type == "string_content":
                                    key_text = get_node_text(grandchild, source)
                                    # Store the brace position and key
                                    brace_row, brace_col = child.start_point
                                    brace_positions.append((brace_row, brace_col, key_text))
                                    break
            
            # Determine which braces we're inside based on cursor position
            lines = text.split('\n')
            brace_depth = 0
            path_keys = []
            
            for row_idx in range(len(lines)):
                line = lines[row_idx]
                end_col = len(line) if row_idx < cursor_row else cursor_col
                
                for col_idx in range(end_col):
                    char = line[col_idx]
                    if char == '{':
                        # Check if this brace has an associated key
                        for brace_row, brace_col, key in brace_positions:
                            if brace_row == row_idx and brace_col == col_idx:
                                path_keys.append((brace_depth, key))
                                break
                        brace_depth += 1
                    elif char == '}':
                        brace_depth -= 1
                        # Remove keys at this depth
                        path_keys = [(d, k) for d, k in path_keys if d < brace_depth]
            
            # Extract just the keys in order
            path = [key for depth, key in sorted(path_keys)]
            return path
            
        else:
            # YAML - try the tree-based approach
            node = find_node_at_position(tree.root_node, cursor_row, cursor_col)
            
            if not node:
                node = tree.root_node
            
            # Get the path from root to this node
            path = get_object_path_to_node(node, source, format_type)
            
            return path
        
    except Exception as e:
        # If parsing fails, return empty path
        return []
