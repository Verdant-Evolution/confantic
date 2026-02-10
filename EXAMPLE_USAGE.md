# Autocomplete Feature Example

This document demonstrates how the new autocomplete feature works in Confantic.

## Setup

Create a Pydantic model for your configuration:

```python
# server_config.py
from pydantic import BaseModel
from typing import Optional

class ServerConfig(BaseModel):
    hostname: str
    port: int = 8080
    debug: bool = False
    max_connections: int = 100
    timeout: Optional[int] = None
    ssl_enabled: bool = True
    log_level: str = "INFO"
```

## Usage

Start Confantic with your model:

```bash
confantic server_config.py:ServerConfig config.json
```

## Autocomplete in Action

### 1. JSON Editing

When editing a JSON file, start typing a key within quotes:

```json
{
  "h
```

**Result**: The autocomplete popup appears showing `hostname` as a suggestion.

Press **Tab** to accept, and it becomes:

```json
{
  "hostname
```

### 2. YAML Editing

When editing a YAML file, start typing at the beginning of a line:

```yaml
h
```

**Result**: The autocomplete popup shows `hostname`.

### 3. Filtering

Type more characters to filter suggestions:

```yaml
ma
```

**Result**: Shows only `max_connections` (the only field starting with "ma").

### 4. Navigation

Use arrow keys to navigate when multiple suggestions match:

```yaml
d
```

**Result**: Shows `debug` (only match for "d").

Type just `s`:

```yaml
s
```

**Result**: Shows `ssl_enabled` (only match for "s").

## Keyboard Shortcuts

- **↑** / **↓**: Navigate through suggestions
- **Tab**: Accept the highlighted suggestion
- **ESC**: Hide the autocomplete popup
- **Ctrl+S**: Save the file
- **Ctrl+Q**: Quit the editor
- **F5** / **Ctrl+V**: Validate the configuration

## Tips

1. The autocomplete only appears when typing keys, not values
2. Suggestions are filtered case-insensitively
3. The popup automatically hides when moving away from a key position
4. You can continue typing to filter suggestions or press ESC to dismiss

## Example Session

1. Open editor: `confantic server_config.py:ServerConfig config.json`
2. Type `{` and press Enter
3. Type `  "h` - autocomplete shows "hostname"
4. Press Tab - "hostname" is inserted
5. Complete the entry: `": "localhost"`
6. Continue adding more fields with autocomplete assistance
