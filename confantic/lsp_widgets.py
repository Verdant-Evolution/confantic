"""UI widgets for LSP feedback."""
from textual.containers import Container
from textual.widgets import Static


class DiagnosticsPopup(Static):
    """A popup widget to display LSP diagnostics."""

    DEFAULT_CSS = """
    DiagnosticsPopup {
        position: absolute;
        bottom: 2;
        right: 2;
        width: 60;
        height: auto;
        max-height: 15;
        background: $panel;
        border: solid $primary;
        padding: 1;
        display: none;
    }
    
    DiagnosticsPopup.visible {
        display: block;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self.diagnostics = []

    def update_diagnostics(self, diagnostics: list[dict]):
        """Update the displayed diagnostics."""
        self.diagnostics = diagnostics
        
        if not diagnostics:
            self.remove_class("visible")
            self.update("")
            return

        # Format diagnostics for display
        lines = ["LSP Diagnostics:"]
        for diag in diagnostics[:5]:  # Show max 5 diagnostics
            severity = diag.get("severity", 1)
            severity_str = {1: "ERROR", 2: "WARNING", 3: "INFO", 4: "HINT"}.get(
                severity, "UNKNOWN"
            )
            message = diag.get("message", "")
            
            # Get range information
            range_info = diag.get("range", {})
            start = range_info.get("start", {})
            line = start.get("line", 0) + 1  # Convert to 1-indexed
            char = start.get("character", 0)
            
            lines.append(f"[{severity_str}] Line {line}:{char}")
            lines.append(f"  {message}")

        if len(diagnostics) > 5:
            lines.append(f"... and {len(diagnostics) - 5} more")

        self.update("\n".join(lines))
        self.add_class("visible")


class CompletionPopup(Static):
    """A popup widget to display LSP completion suggestions."""

    DEFAULT_CSS = """
    CompletionPopup {
        width: 40;
        height: auto;
        max-height: 10;
        background: $panel;
        border: solid $accent;
        padding: 1;
        display: none;
    }
    
    CompletionPopup.visible {
        display: block;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self.completions = []

    def update_completions(self, completions: list[dict]):
        """Update the displayed completions."""
        self.completions = completions
        
        if not completions:
            self.remove_class("visible")
            self.update("")
            return

        # Format completions for display
        lines = ["Suggestions:"]
        for item in completions[:8]:  # Show max 8 completions
            label = item.get("label", "")
            detail = item.get("detail", "")
            if detail:
                lines.append(f"  • {label} - {detail}")
            else:
                lines.append(f"  • {label}")

        if len(completions) > 8:
            lines.append(f"  ... and {len(completions) - 8} more")

        self.update("\n".join(lines))
        self.add_class("visible")

    def hide(self):
        """Hide the completion popup."""
        self.remove_class("visible")
        self.update("")
