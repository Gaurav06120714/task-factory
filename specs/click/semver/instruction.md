# Feature Request: Semantic Version Parameter Type

## Overview
Add a parameter type that accepts semantic version strings such as `1.2.3-rc.1` and can restrict them to a range. It must be available as `click.SemVer`.

## Signature
```python
click.SemVer(min: str | None = None, max: str | None = None)
```
`convert(value, param, ctx)` returns the version as a `str`.

## Accepted values
- A version is `MAJOR.MINOR.PATCH`: exactly three dot-separated parts, each made only of digits.
- It may be followed by a pre-release part after `-` (e.g. `1.2.3-rc.1`) and/or build metadata after `+` (e.g. `1.2.3+build.1`, `1.2.3-rc.1+build.1`).
- A valid value is returned unchanged:
  - `click.SemVer().convert('1.2.3', None, None)` returns `'1.2.3'`
  - `click.SemVer().convert('1.2.3-rc.1+build.1', None, None)` returns `'1.2.3-rc.1+build.1'`
  - `'1.2.3-invalid'` and `'1.2.3+invalid'` are valid and returned unchanged.

## Invalid values
Anything else, including values that are not strings, fails with `click.BadParameter` and the message `{value!r} is not a valid semantic version.`:
- `'1.2'` → `'1.2' is not a valid semantic version.`
- `''` → `'' is not a valid semantic version.`
- `None` → `None is not a valid semantic version.`
- `123` → `123 is not a valid semantic version.`

## Range
- `min` and `max` are version strings and are inclusive. Versions are compared by MAJOR, then MINOR, then PATCH, as numbers.
- A value outside the range fails with `click.BadParameter` and the message `{value!r} is not in the range {low} to {high}.`, where a missing bound is written as `-`:
  - `SemVer(min='1.2.4')` with `'1.2.3'` → `'1.2.3' is not in the range 1.2.4 to -.`
  - `SemVer(max='1.2.2')` with `'1.2.3'` → `'1.2.3' is not in the range - to 1.2.2.`
  - `SemVer(min='1.2.3')` and `SemVer(max='1.2.3')` both accept `'1.2.3'`.
