As a developer, you are tasked with adding support for custom ANSI colors in the Click library. The feature should be implemented under `src/click/custom_color.py` and documented in `docs/source/custom_color.rst`.

**Public API:**
- `custom_color(color_code: str) -> str`: This function takes a string representing a custom ANSI color code and returns a string representing the valid ANSI escape sequence.

**Behaviour:**
- The function should convert the input color code into a valid ANSI escape sequence.
- If the input color code is invalid, the function should raise a `ValueError` with an appropriate error message.

**User-facing Messages:**
- The error message for invalid color codes should be "Invalid color code: <color_code>".
