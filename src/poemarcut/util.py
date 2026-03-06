"""General utility functions for PoEMarcut."""


def shortest_unique_prefix(target_string: str, string_list: list[str]) -> str:
    """Return the shortest unique prefix substring of a target string in a string list.

    Given a list of strings and a target string within that list,
    returns the shortest prefix substring of the target string that
    does not appear as a prefix substring of any other string in the list.

    Useful for calculating the shortest unique prefix for a currency name in the merchant tab dropdown list,
    to minimize the number of characters that need to be typed to select that currency.
    """
    # Ensure the target string is actually in the list, and handle potential duplicates by comparing to *other* strings.
    other_strings = [s for s in string_list if s != target_string]

    for length in range(1, len(target_string) + 1):
        prefix = target_string[:length]
        is_unique_prefix = True
        for other in other_strings:
            # Check if 'other' starts with the current prefix
            if other.startswith(prefix):
                is_unique_prefix = False
                break

        if is_unique_prefix:
            return prefix

    # If no unique prefix is found (which shouldn't happen if all strings are unique),
    # the entire string is the unique beginning substring.
    return target_string
