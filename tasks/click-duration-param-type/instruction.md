# Add a `click.Duration` parameter type

Command-line tools often take time spans such as a timeout, a retry interval or a cache lifetime. Today click users must accept a plain integer and document the unit, or write their own type. Add a built-in parameter type that turns human-readable durations into `datetime.timedelta` objects.

## Requirements

1. Add a new parameter type class `Duration` in `click.types` and export it as `click.Duration`.
2. `Duration(min=None, max=None)`: both arguments are optional `datetime.timedelta` bounds.
3. Accepted input (leading and trailing whitespace is ignored):
   - A bare non-negative integer is a number of **seconds**, e.g. `90` → 90 seconds.
   - Otherwise, one or more `<non-negative integer><unit>` components with no spaces between them. The units are `d` (days), `h` (hours), `m` (minutes) and `s` (seconds). Units are case-insensitive. Each unit may appear **at most once**, and the units must appear **in the order d, h, m, s**. Examples: `5m`, `1h30m`, `2d4h`, `1D2H3M4S`.
   - Anything else is invalid, for example an empty string, `1.5h`, `-5`, `30m1h` (wrong order), `1h1h` (repeated unit), `1w` (unknown unit) and `1h 30m` (space inside).
4. The converted value is a `datetime.timedelta`. A value that is already a `timedelta` is returned unchanged (after the range check).
5. Invalid input fails with the message `{value!r} is not a valid duration.`, e.g. `'abc' is not a valid duration.`
6. If `min` and/or `max` are given, the bounds are inclusive. A value outside them fails with the message `{value!r} is not in the range {low} to {high}.`. Here `low` and `high` are `str()` of the bounds, and a missing bound is written as `-`. For example, with `max=timedelta(hours=1)` the input `2h` fails with `'2h' is not in the range - to 1:00:00.`
7. Like other built-in types:
   - `name` is `"duration"`, so the default metavar in `--help` is `DURATION`.
   - `repr()` returns `"Duration"`.
   - `to_info_dict()` includes `"min"` and `"max"` as a number of seconds (`float`) or `None`, alongside the usual `"param_type"` and `"name"` keys.
8. Do not change the behaviour of any existing type or command.
