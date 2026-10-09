import re


def version_tuple(value):
    """'1.1.34' -> (1, 1, 34); suffixes such as '-qa' are ignored; junk -> ()."""
    numbers = re.findall(r"\d+", str(value or "").split("-")[0])
    return tuple(int(n) for n in numbers[:4])


def is_newer(candidate, current):
    a, b = version_tuple(candidate), version_tuple(current)
    return bool(a) and a > b
