# Feature Request: Parse Human-Readable Byte Sizes into Integers

## Overview
The feature request is to implement a `ByteSize` class in the `click` library that converts human-readable byte sizes into integers. This class should be available as `click.ByteSize`.

## Signature
```python
class ByteSize(ParamType):
    def __init__(self, min: int | None = None, max: int | None = None) -> None:
        pass

    def convert(
        self, value: t.Any, param: Parameter | None, ctx: Context | None
    ) -> int:
        pass
```

## Behavior

### Accepted formats
- Leading and trailing whitespace is ignored and units are case-insensitive.
- A bare non-negative integer such as `512` is a number of bytes.
- Otherwise the value is a number (it may have a decimal part, e.g. `1.5K`) followed by exactly one unit:
  `K` = 1024, `M` = 1024², `G` = 1024³, `T` = 1024⁴, `P` = 1024⁵, `E` = 1024⁶, `Z` = 1024⁷, `Y` = 1024⁸ bytes.
  The result is truncated to an `int`.
- A value that is already an `int` is returned unchanged (the same object), after the range check below.
- `min` and `max` are inclusive bounds in bytes; a missing bound is shown as `-` in the error message.
- Invalid input exits with usage error status 2 (as for other click parameter types).

### Normal Input
- **Input:** "1024K"
- **Output:** 1048576

### Edge Cases

#### Empty String
- **Input:** ""
- **Output:** Error message: `'' is not a valid byte size.`

#### Invalid Characters
- **Input:** "abc"
- **Output:** Error message: `'abc' is not a valid byte size.`

#### Invalid Unit
- **Input:** "1.5h"
- **Output:** Error message: `'1.5h' is not a valid byte size.`

#### Negative Number
- **Input:** "-5"
- **Output:** Error message: `'-5' is not a valid byte size.`

#### Mixed Units
- **Input:** "30m1h"
- **Output:** Error message: `'30m1h' is not a valid byte size.`

#### Invalid Unit Order
- **Input:** "1h1h"
- **Output:** Error message: `'1h1h' is not a valid byte size.`

#### Non-Standard Units
- **Input:** "1w"
- **Output:** Error message: `'1w' is not a valid byte size.`

#### Multiple Spaces
- **Input:** "1h 30m"
- **Output:** Error message: `'1h 30m' is not a valid byte size.`

#### Unit with Leading Space
- **Input:** "h"
- **Output:** Error message: `'h' is not a valid byte size.`

#### Unit with Trailing Space
- **Input:** "1024Z1"
- **Output:** Error message: `'1024Z1' is not a valid byte size.`

### Bounds

#### Minimum Bound
- **Input:** "512" with min=1024
- **Output:** Error message: `'512' is not in the range 1024 to -.`

#### Maximum Bound
- **Input:** "1025" with max=1024
- **Output:** Error message: `'1025' is not in the range - to 1024.`

#### Both Bounds
- **Input:** "2049" with min=1024 and max=2048
- **Output:** Error message: `'2049' is not in the range 1024 to 2048.`

## Help Metavar
- **Output:** `--size BYTE_SIZE`
