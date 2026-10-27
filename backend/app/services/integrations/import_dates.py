"""Date interpretation is a local, explicitly confirmed parsing choice."""
import re
from datetime import date

_NUMERIC = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")


def _interpret(value, order):
    match = _NUMERIC.fullmatch(str(value or "").strip())
    if not match:
        return value
    first, second, year = map(int, match.groups())
    day, month = (first, second) if order == "dmy" else (second, first)
    return date(year, month, day).isoformat()


def date_preview(rows, column, row_numbers):
    result = []
    for row, number in zip(rows, row_numbers, strict=True):
        value = row.get(column)
        if not _NUMERIC.fullmatch(str(value or "").strip()):
            continue
        interpretations = {}
        for order in ("dmy", "mdy"):
            try:
                interpretations[order] = _interpret(value, order)
            except ValueError:
                interpretations[order] = None
        if interpretations["dmy"] and interpretations["mdy"] and interpretations["dmy"] != interpretations["mdy"]:
            result.append({"row": number, "value": value, **interpretations})
    return result


def resolve_dates(rows, column, order):
    if order not in {None, "dmy", "mdy"}:
        raise ValueError("Invalid date order")
    result = []
    for row in rows:
        item = dict(row)
        value = item.get(column)
        if _NUMERIC.fullmatch(str(value or "").strip()):
            if order:
                try:
                    item[column] = _interpret(value, order)
                except ValueError:
                    raise ValueError("A source date is invalid for the selected date order") from None
            else:
                choices = set()
                for candidate in ("dmy", "mdy"):
                    try:
                        choices.add(_interpret(value, candidate))
                    except ValueError:
                        pass
                if len(choices) != 1:
                    raise ValueError("Select a date order before importing ambiguous or invalid dates")
                item[column] = choices.pop()
        result.append(item)
    return result
