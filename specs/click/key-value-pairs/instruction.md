# Feature Request: Parse KEY=VALUE pairs into a list of tuples

## Description
The feature request is to implement a parameter type in the `click` library that can parse a string of KEY=VALUE pairs into a list of tuples. Pairs are separated by commas. Each tuple holds the key and the value as strings, with surrounding whitespace stripped. The type is available as `click.KeyValuePairs`. The implementation should handle various edge cases and provide appropriate error messages.

## Signature
```python
class KeyValuePairs(ParamType):
    def __init__(self, delimiter: str = '=') -> None:
        self.delimiter = delimiter

    def convert(
        self, value: t.Any, param: Parameter | None, ctx: Context | None
    ) -> t.List[t.Tuple[str, str]]:
        pass
```

## Behavior

### Normal Input
- **Input:** `'key1=value1,key2=value2'`
- **Output:** `[('key1', 'value1'), ('key2', 'value2')]`

### Edge Cases

#### Empty String
- **Input:** `''`
- **Error Message:** `'' is not a valid KEY=VALUE pair.`

#### Single Pair
- **Input:** `'key=value'`
- **Output:** `[('key', 'value')]`

#### Multiple Pairs
- **Input:** `'key1=value1,key2=value2,key3=value3'`
- **Output:** `[('key1', 'value1'), ('key2', 'value2'), ('key3', 'value3')]`

#### Trailing Comma
- **Input:** `'key1=value1,'`
- **Error Message:** `'key1=value1,' is not a valid KEY=VALUE pair.`

#### Leading Comma
- **Input:** `',key1=value1'`
- **Error Message:** `',key1=value1' is not a valid KEY=VALUE pair.`

#### Multiple Delimiters
- **Input:** `'key1:value1,key2:value2'`
- **Delimiter:** `':'`
- **Output:** `[('key1', 'value1'), ('key2', 'value2')]`

#### Whitespace Around Delimiter
- **Input:** `'key1 = value1, key2 = value2'`
- **Output:** `[('key1', 'value1'), ('key2', 'value2')]`

#### Missing Value
- **Input:** `'key1,key2=value2'`
- **Error Message:** `'key1,key2=value2' is not a valid KEY=VALUE pair.`

#### Extra Value
- **Input:** `'key1=value1,key2=value2=value3'`
- **Error Message:** `'key1=value1,key2=value2=value3' is not a valid KEY=VALUE pair.`

#### Non-String Input
- **Input:** `123`
- **Error Message:** `123 is not a valid string of KEY=VALUE pairs.`

#### Invalid Delimiter
- **Input:** `'key1=value1'`
- **Delimiter:** `''`
- **Error Message:** `empty separator`

#### Unicode Key
- **Input:** `'keyé=value1'`
- **Output:** `[('keyé', 'value1')]`

#### Unicode Value
- **Input:** `'key1=évalue'`
- **Output:** `[('key1', 'évalue')]`

#### Non-ASCII Delimiter
- **Input:** `'key1=value1'`
- **Delimiter:** `'é'`
- **Error Message:** `'key1=value1' is not a valid KEY=VALUE pair.`

## Notes
- The implementation should handle both ASCII and Unicode characters for keys and values.
- The delimiter should be configurable and default to `'='`.
- The implementation should raise a `click.BadParameter` with the appropriate error message for invalid inputs.
- The implementation should raise a `ValueError` if an empty delimiter is provided.
