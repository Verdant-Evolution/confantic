"""Tree-sitter utilities for parsing JSON and YAML."""

from typing import Optional, Literal
import tree_sitter
import tree_sitter_json
import tree_sitter_yaml


# Create language objects
JSON_LANGUAGE = tree_sitter.Language(tree_sitter_json.language())
YAML_LANGUAGE = tree_sitter.Language(tree_sitter_yaml.language())

# Create parsers
JSON_PARSER = tree_sitter.Parser(JSON_LANGUAGE)
YAML_PARSER = tree_sitter.Parser(YAML_LANGUAGE)


def parse_document(text: str, format_type: Literal["json", "yaml"]) -> tree_sitter.Tree:
    """
    Parse a document using tree-sitter.
    
    Args:
        text: The document text to parse
        format_type: Either "json" or "yaml"
        
    Returns:
        A tree-sitter Tree object
    """
    parser = JSON_PARSER if format_type == "json" else YAML_PARSER
    return parser.parse(bytes(text, 'utf8'))


def find_node_at_position(root: tree_sitter.Node, row: int, col: int) -> Optional[tree_sitter.Node]:
    """
    Find the most specific (deepest) node containing the given position.
    
    For incomplete trees, if the position is beyond the tree, return the last relevant node.
    
    Args:
        root: The root node to search from
        row: Zero-indexed row number
        col: Zero-indexed column number
        
    Returns:
        The deepest node containing the position, or None
    """
    def is_position_in_node(node: tree_sitter.Node) -> bool:
        """Check if position is within node bounds"""
        start_row, start_col = node.start_point
        end_row, end_col = node.end_point
        
        # Position is before node
        if row < start_row or (row == start_row and col < start_col):
            return False
        
        # Position is after node
        if row > end_row or (row == end_row and col > end_col):
            return False
            
        return True
    
    def find_deepest(node: tree_sitter.Node) -> Optional[tree_sitter.Node]:
        """Recursively find the deepest node containing position"""
        if not is_position_in_node(node):
            return None
        
        # Try children first to find more specific node
        for child in node.children:
            result = find_deepest(child)
            if result:
                return result
        
        # No child contains the position, return this node
        return node
    
    result = find_deepest(root)
    
    # If no node found (position is beyond tree), return the root or last relevant node
    if not result and root.type != "ERROR":
        # For incomplete trees, the ERROR node itself might be useful
        return root
    
    return result


def get_node_text(node: tree_sitter.Node, source: bytes) -> str:
    """Extract the text content of a node."""
    return source[node.start_byte:node.end_byte].decode('utf8')


def find_parent_object_node(node: tree_sitter.Node, format_type: Literal["json", "yaml"]) -> Optional[tree_sitter.Node]:
    """
    Find the parent object/mapping node that contains the given node.
    
    This handles both complete and incomplete (ERROR) trees.
    
    Args:
        node: The starting node
        format_type: Either "json" or "yaml"
        
    Returns:
        The parent object/mapping node, or None
    """
    if format_type == "json":
        object_type = "object"
    else:
        object_type = "block_mapping"
    
    current = node
    while current:
        if current.type == object_type:
            return current
        
        # For incomplete JSON/YAML, check if ERROR node contains object-like structure
        if current.type == "ERROR":
            # Check if this ERROR node has object-like children (pair nodes for JSON)
            if format_type == "json":
                # If it has pairs or opening brace, treat it as an object
                for child in current.children:
                    if child.type in ["pair", "{"]:
                        return current
            else:
                # For YAML, check for block_mapping_pair
                for child in current.children:
                    if child.type == "block_mapping_pair":
                        return current
        
        current = current.parent
    
    return None


def extract_object_keys(object_node: tree_sitter.Node, source: bytes, format_type: Literal["json", "yaml"]) -> list[str]:
    """
    Extract all keys from an object/mapping node.
    
    This handles both complete objects and ERROR nodes with object-like structure.
    
    Args:
        object_node: The object, block_mapping, or ERROR node
        source: The source text as bytes
        format_type: Either "json" or "yaml"
        
    Returns:
        List of key names
    """
    keys = []
    
    if format_type == "json":
        # In JSON, keys are in "pair" nodes
        # Handle both complete objects and ERROR nodes
        for child in object_node.children:
            if child.type == "pair":
                # First child of pair is the key (a string node)
                key_node = child.children[0] if child.children else None
                if key_node and key_node.type == "string":
                    # Extract text from string node (including quotes)
                    # Then look for string_content child
                    for grandchild in key_node.children:
                        if grandchild.type == "string_content":
                            key_text = get_node_text(grandchild, source)
                            keys.append(key_text)
                            break
    else:
        # In YAML, keys are in "block_mapping_pair" nodes
        for child in object_node.children:
            if child.type == "block_mapping_pair":
                # First child is usually the key
                if child.children:
                    # Navigate through flow_node -> plain_scalar -> string_scalar
                    key_node = child.children[0]
                    while key_node and key_node.type in ["flow_node", "plain_scalar"]:
                        if key_node.children:
                            key_node = key_node.children[0]
                        else:
                            break
                    
                    if key_node and key_node.type == "string_scalar":
                        key_text = get_node_text(key_node, source)
                        keys.append(key_text)
    
    return keys


def get_object_path_to_node(node: tree_sitter.Node, source: bytes, format_type: Literal["json", "yaml"]) -> list[str]:
    """
    Get the path of object keys from root to the given node.
    
    This handles both complete and incomplete (ERROR) trees.
    
    Args:
        node: The target node
        source: The source text as bytes
        format_type: Either "json" or "yaml"
        
    Returns:
        List of key names representing the path
    """
    path = []
    current = node
    
    if format_type == "json":
        # Walk up the tree, looking for opening braces that indicate nesting
        # For each brace, look backwards to find the key
        brace_positions = []
        temp = current
        
        # Collect all ancestor nodes
        ancestors = []
        while temp:
            ancestors.append(temp)
            temp = temp.parent
        
        # Look through ancestors for opening braces
        for ancestor in ancestors:
            if ancestor.type == "{":
                # Found an opening brace - look for preceding key
                # Check siblings before this brace
                if ancestor.parent:
                    found_key = False
                    for i, sibling in enumerate(ancestor.parent.children):
                        if sibling == ancestor:
                            # Look at previous siblings
                            # Pattern: ... "key" : {
                            if i >= 2:
                                colon = ancestor.parent.children[i - 1]
                                key_node = ancestor.parent.children[i - 2]
                                
                                if colon.type == ":" and key_node.type == "string":
                                    # Extract key text
                                    for child in key_node.children:
                                        if child.type == "string_content":
                                            key_text = get_node_text(child, source)
                                            path.insert(0, key_text)
                                            found_key = True
                                            break
                            break
                            
            elif ancestor.type == "pair":
                # In a complete tree, pairs with object values indicate nesting
                if len(ancestor.children) >= 3:
                    key_node = ancestor.children[0]
                    value_node = ancestor.children[2] if len(ancestor.children) > 2 else None
                    
                    if key_node.type == "string" and value_node and value_node.type == "object":
                        # This pair has an object value - check if we're inside it
                        temp = current
                        is_inside = False
                        while temp and temp != ancestor:
                            if temp == value_node:
                                is_inside = True
                                break
                            temp = temp.parent
                        
                        if is_inside:
                            # Extract key
                            for child in key_node.children:
                                if child.type == "string_content":
                                    key_text = get_node_text(child, source)
                                    path.insert(0, key_text)
                                    break
                                    
    else:
        # YAML
        while current:
            if current.type == "block_mapping_pair":
                # Get the key
                if current.children:
                    key_node = current.children[0]
                    while key_node and key_node.type in ["flow_node", "plain_scalar"]:
                        if key_node.children:
                            key_node = key_node.children[0]
                        else:
                            break
                    
                    if key_node and key_node.type == "string_scalar":
                        key_text = get_node_text(key_node, source)
                        # Check if value is a mapping
                        for child in current.children:
                            if child.type == "block_node":
                                for grandchild in child.children:
                                    if grandchild.type == "block_mapping":
                                        path.insert(0, key_text)
                                        break
                                break
            current = current.parent
    
    return path


def is_in_key_position(node: tree_sitter.Node, format_type: Literal["json", "yaml"]) -> bool:
    """
    Check if the cursor position (represented by node) is in a position where a key should be typed.
    
    Args:
        node: The node at cursor position
        format_type: Either "json" or "yaml"
        
    Returns:
        True if cursor is in key position, False otherwise
    """
    if format_type == "json":
        # In JSON, we're in key position if:
        # 1. We're in a string that's the first child of a pair
        # 2. We're in an object but not in a value
        
        # Check if we're in a string node
        if node.type == "string" or node.type == "string_content":
            # Check if parent is a pair and we're the first child (the key)
            parent = node.parent
            while parent and parent.type in ["string", "string_content"]:
                parent = parent.parent
            
            if parent and parent.type == "pair":
                # Check if we're in the first child (key position)
                if parent.children and parent.children[0].type == "string":
                    return True
        
        # Check if we're right after an opening brace or comma in an object
        if node.type in ["{", ","]:
            return True
        
        # If we're in an object but not in a complete pair, we might be typing a new key
        parent = node
        while parent:
            if parent.type == "object":
                # We're in an object - check if we're not in a value position
                return True
            if parent.type == "pair":
                # We're in a pair - check if we're in key or value
                # If we're past the colon, we're in value position
                for child in parent.children:
                    if child.type == ":":
                        # There's a colon, so if our node comes after it, we're in value
                        return False
                # No colon yet, so we might be in key position
                return True
            parent = parent.parent
            
    else:
        # In YAML, we're in key position if:
        # 1. We're at the start of a line in a mapping
        # 2. We're in a string_scalar that's a key
        
        if node.type == "string_scalar":
            # Check if parent chain leads to a block_mapping_pair with us as first child
            parent = node.parent
            while parent and parent.type in ["plain_scalar", "flow_node"]:
                parent = parent.parent
            
            if parent and parent.type == "block_mapping_pair":
                return True
    
    return False
