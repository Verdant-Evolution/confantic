"""LSP Client for communicating with vscode-json-languageserver."""
import json
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Optional
import os


class LSPClient:
    """A simple LSP client to communicate with the JSON language server."""

    def __init__(self, schema: dict[str, Any], file_uri: str):
        """
        Initialize LSP client.
        
        Args:
            schema: JSON schema for validation
            file_uri: URI of the file being edited (e.g., file:///path/to/file.json)
        """
        self.schema = schema
        self.file_uri = file_uri
        self.process: Optional[subprocess.Popen] = None
        self.message_id = 0
        self.diagnostics: list[dict] = []
        self.completions: list[dict] = []
        self._lock = threading.Lock()
        self._response_handlers: dict[int, Callable] = {}
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        """Start the LSP server process."""
        # Find the language server executable
        node_modules_path = Path(__file__).parent.parent / "node_modules"
        server_path = node_modules_path / ".bin" / "vscode-json-languageserver"
        
        if not server_path.exists():
            # Try alternative path
            server_path = node_modules_path / "vscode-json-languageserver" / "bin" / "vscode-json-languageserver"
        
        if not server_path.exists():
            raise RuntimeError(
                f"vscode-json-languageserver not found. Please install it with: npm install"
            )

        # Start the LSP server
        self.process = subprocess.Popen(
            ["node", str(server_path), "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        self._running = True
        self._reader_thread = threading.Thread(target=self._read_messages, daemon=True)
        self._reader_thread.start()

        # Initialize the LSP connection
        self._initialize()

    def _send_message(self, message: dict) -> int:
        """Send a JSON-RPC message to the server."""
        if not self.process or not self.process.stdin:
            raise RuntimeError("LSP server not started")

        message_id = self.message_id
        self.message_id += 1

        if "id" not in message:
            message["id"] = message_id

        content = json.dumps(message)
        content_bytes = content.encode("utf-8")
        header = f"Content-Length: {len(content_bytes)}\r\n\r\n"

        try:
            self.process.stdin.write(header.encode("utf-8"))
            self.process.stdin.write(content_bytes)
            self.process.stdin.flush()
        except Exception as e:
            # Silently ignore write errors to avoid crashing
            pass

        return message_id

    def _read_messages(self):
        """Read messages from the LSP server in a background thread."""
        if not self.process or not self.process.stdout:
            return

        buffer = b""
        while self._running:
            try:
                chunk = self.process.stdout.read(1)
                if not chunk:
                    break
                buffer += chunk

                # Check if we have a complete header
                if b"\r\n\r\n" in buffer:
                    header_end = buffer.index(b"\r\n\r\n")
                    header = buffer[:header_end].decode("utf-8")
                    buffer = buffer[header_end + 4 :]

                    # Parse Content-Length
                    content_length = 0
                    for line in header.split("\r\n"):
                        if line.startswith("Content-Length:"):
                            content_length = int(line.split(":")[1].strip())
                            break

                    # Read the content
                    while len(buffer) < content_length:
                        chunk = self.process.stdout.read(
                            content_length - len(buffer)
                        )
                        if not chunk:
                            break
                        buffer += chunk

                    if len(buffer) >= content_length:
                        content = buffer[:content_length]
                        buffer = buffer[content_length:]

                        # Parse and handle the message
                        try:
                            message = json.loads(content.decode("utf-8"))
                            self._handle_message(message)
                        except json.JSONDecodeError:
                            pass
            except Exception:
                # Silently ignore read errors
                if not self._running:
                    break

    def _handle_message(self, message: dict):
        """Handle incoming messages from the LSP server."""
        if "method" in message:
            # This is a notification or request from server
            if message["method"] == "textDocument/publishDiagnostics":
                params = message.get("params", {})
                if params.get("uri") == self.file_uri:
                    with self._lock:
                        self.diagnostics = params.get("diagnostics", [])
        elif "id" in message:
            # This is a response to our request
            msg_id = message["id"]
            with self._lock:
                if msg_id in self._response_handlers:
                    handler = self._response_handlers.pop(msg_id)
                    handler(message)

    def _initialize(self):
        """Send the initialize request to the LSP server."""
        init_message = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "processId": os.getpid(),
                "rootUri": None,
                "capabilities": {
                    "textDocument": {
                        "completion": {"completionItem": {"snippetSupport": False}},
                        "publishDiagnostics": {},
                    }
                },
            },
        }

        def on_init_response(response):
            # Send initialized notification
            self._send_message(
                {"jsonrpc": "2.0", "method": "initialized", "params": {}}
            )

        msg_id = self._send_message(init_message)
        with self._lock:
            self._response_handlers[msg_id] = on_init_response

    def did_open(self, text: str):
        """Notify the server that a document was opened."""
        message = {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": self.file_uri,
                    "languageId": "json",
                    "version": 1,
                    "text": text,
                }
            },
        }
        
        # Register the schema
        self._register_schema()
        self._send_message(message)

    def _register_schema(self):
        """Register the JSON schema with the language server."""
        # Configure the schema association
        settings_message = {
            "jsonrpc": "2.0",
            "method": "workspace/didChangeConfiguration",
            "params": {
                "settings": {
                    "json": {
                        "schemas": [
                            {
                                "fileMatch": [self.file_uri],
                                "schema": self.schema,
                            }
                        ]
                    }
                }
            },
        }
        self._send_message(settings_message)

    def did_change(self, text: str, version: int = 1):
        """Notify the server that the document content changed."""
        message = {
            "jsonrpc": "2.0",
            "method": "textDocument/didChange",
            "params": {
                "textDocument": {"uri": self.file_uri, "version": version},
                "contentChanges": [{"text": text}],
            },
        }
        self._send_message(message)

    def completion(
        self, text: str, line: int, character: int, callback: Callable[[list], None]
    ):
        """Request completion items at a specific position."""
        message = {
            "jsonrpc": "2.0",
            "method": "textDocument/completion",
            "params": {
                "textDocument": {"uri": self.file_uri},
                "position": {"line": line, "character": character},
            },
        }

        def on_completion_response(response):
            result = response.get("result")
            items = []
            if result:
                if isinstance(result, dict):
                    items = result.get("items", [])
                elif isinstance(result, list):
                    items = result
            callback(items)

        msg_id = self._send_message(message)
        with self._lock:
            self._response_handlers[msg_id] = on_completion_response

    def get_diagnostics(self) -> list[dict]:
        """Get the current diagnostics for the document."""
        with self._lock:
            return self.diagnostics.copy()

    def stop(self):
        """Stop the LSP server."""
        self._running = False
        if self.process:
            try:
                # Send shutdown request
                self._send_message({"jsonrpc": "2.0", "method": "shutdown"})
                # Send exit notification
                self._send_message({"jsonrpc": "2.0", "method": "exit"})
            except Exception:
                pass

            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=1)
