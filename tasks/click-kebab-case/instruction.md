# Feature Request: Convert a Delimited List into Kebab-Case

## Overview
The feature request is to implement a parameter type in the `click` library that converts a comma-separated list into kebab-case. The implementation should be available as `click.KebabCase`.

## Signature
```python
class KebabCase(ParamType):
    def __init__(self, min: int | None = None, max: int | None = None) -> None:
        self.min = min
        self.max = max

    def convert(
        self, value: t.Any, param: Parameter | None, ctx: Context | None
    ) -> str:
        # Implementation details
```

## Behavior

### Normal Input
- **Input:** `'apple,banana,cherry'`
- **Output:** `'apple-banana-cherry'`

### Edge Cases

#### Empty Input
- **Input:** `''`
- **Output:** `''`

#### Non-String Input
- **Input:** `123`
- **Error Message:** `123 is not a valid string.`

#### Minimum Boundary
- **Input:** `'apple,banana,cherry'` with `min=3`
- **Output:** `'apple-banana-cherry'`

#### Maximum Boundary
- **Input:** `'apple,banana,cherry'` with `max=3`
- **Output:** `'apple-banana-cherry'`

#### Minimum Violation
- **Input:** `'apple,banana,cherry'` with `min=4`
- **Error Message:** `'apple,banana,cherry' does not have the correct number of items. Expected 4 to -.`

#### Maximum Violation
- **Input:** `'apple,banana,cherry'` with `max=2`
- **Error Message:** `'apple,banana,cherry' does not have the correct number of items. Expected - to 2.`

#### Leading Space
- **Input:** `' apple,banana,cherry'`
- **Output:** `'apple-banana-cherry'`

#### Trailing Space
- **Input:** `'apple,banana,cherry '`
- **Output:** `'apple-banana-cherry'`

#### Multiple Spaces
- **Input:** `'apple,  banana,  cherry'`
- **Output:** `'apple-banana-cherry'`

#### Empty Item
- **Input:** `'apple,,banana'`
- **Output:** `'apple-banana'`

#### Single Item
- **Input:** `'apple'`
- **Output:** `'apple'`

#### All Uppercase
- **Input:** `'APPLE,BANANA,CHERRY'`
- **Output:** `'apple-banana-cherry'`

#### Mixed Case
- **Input:** `'ApPle,BaNaNa,ChErRy'`
- **Output:** `'apple-banana-cherry'`

## Error Messages
- `"{value!r} is not a valid string."`
- `"{value!r} does not have the correct number of items. Expected {low} to {high}."`

## Notes
- The implementation should handle leading, trailing, and multiple spaces within items.
- Empty items should be ignored in the output.
- The output should be in lowercase and separated by hyphens.
