"""General utility functions for PoEMarcut."""


def shortest_unique_prefix(target_string: str, string_list: list[str]) -> str:
    """Return the shortest unique prefix of `target_string` considering list order.

    This function treats only earlier items in `string_list` as potential
    conflicts. The `position` argument may be supplied to indicate which
    occurrence of `target_string` should be disambiguated; if omitted the
    first index of `target_string` in `string_list` is used.

    Args:
        target_string: the string to compute a unique prefix for.
        string_list: list of candidate strings (order matters).
        position: optional explicit index of the occurrence to consider.

    Returns:
        Shortest prefix of `target_string` that does not match the start of any
        string appearing earlier in `string_list`.

    """

    def _resolve_position(pos: int | None) -> int:
        if pos is None:
            try:
                return string_list.index(target_string)
            except ValueError as exc:
                msg = "target_string not found in string_list"
                raise ValueError(msg) from exc
        if pos < 0 or pos >= len(string_list):
            msg = "position out of range for string_list"
            raise IndexError(msg)
        if string_list[pos] != target_string:
            msg = "string at provided position does not match target_string"
            raise ValueError(msg)
        return pos

    position = _resolve_position(None)
    earlier = string_list[:position]

    for length in range(1, len(target_string) + 1):
        prefix = target_string[:length]
        if all(not other.startswith(prefix) for other in earlier):
            return prefix

    return target_string


def shortest_unique_prefixes_in_order(string_list: list[str]) -> list[str]:
    """Compute the shortest unique prefix for each item, honoring list order.

    Each item is disambiguated only against items that appear earlier in the
    list. The first occurrence of a string will therefore usually receive the
    shortest possible prefix.
    """
    prefixes: list[str] = [shortest_unique_prefix(s, string_list) for s in string_list]
    return prefixes
