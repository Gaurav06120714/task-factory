# Add a `click.ByteSize` parameter type

Command-line tools often take byte sizes such as file sizes or memory allocations. Today click users must accept a plain integer and document the unit, or write their own type. Add a built-in parameter type that turns human-readable byte sizes into integers.

## Requirements

1. Add a new parameter type class `ByteSize` in `click.types` and export it as `click.ByteSize`.
2. `ByteSize(min=None, max=None)`: both arguments are optional integer bounds.
3. Accepted input (leading and trailing whitespace is ignored):
   - A bare non-negative integer is a number of **bytes**, e.g. `1024` → 1024 bytes.
   - Otherwise, one or more `<non-negative integer><unit>` components with no spaces between them. The units are `K` (kilobytes), `M` (megabytes), `G` (gigabytes), `T` (terabytes), `P` (petabytes), `E` (exabytes), `Z` (zettabytes), and `Y` (yottabytes). Units are case-insensitive. Each unit may appear **at most once**, and the units must appear **in the order K, M, G, T, P, E, Z, Y**. Examples: `5K`, `1M30G`, `2T4P`, `1Y2Z3E4D`.
   - Anything else is invalid, for example an empty string, `1.5Kb`, `-5`, `30K1M`, `1K1K`, `1W`, `1K 30K`, `K`.
4. The converted value is an integer. A value that is already an integer is returned unchanged (after the range check).
5. Invalid input fails with the message `{value!r} is not a valid byte size.`, e.g. `'abc' is not a valid byte size.`.
6. If `min` and/or `max` are given, the bounds are inclusive. A value outside them fails with the message `{value!r} is not in the range {low} to {high}.`. Here `low` and `high` are `str()` of the bounds, and a missing bound is written as `-`. For example, with `max=1024` the input `2K` fails with `'2K' is not in the range - to 1024.`.
7. Like other built-in types:
   - `name` is `"byte_size"`, so the default metavar in `--help` is `BYTE_SIZE`.
   - `repr()` returns `"ByteSize"`.
   - `to_info_dict()` includes `"min"` and `"max"` as a number of bytes (`int`) or `None`, alongside the usual `"param_type"` and `"name"` keys.
8. Do not change the behaviour of any existing type or command.
