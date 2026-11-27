**Feature Request: Add an option to disable progress bar**

**Public API:**
- `click.progressbar`: A context manager that creates a progress bar. It should accept a `hidden` parameter that defaults to `False`.

**Behaviour:**
- When `hidden=True`, the progress bar should not be displayed.
- When `hidden=False`, the progress bar should be displayed as before.
- The progress bar should be displayed only if the output stream is a terminal.

**User-facing Messages:**
- No additional messages should be added or modified.
- The progress bar should be displayed or hidden based on the `hidden` parameter.
