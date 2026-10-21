"""German spellings for the detection patterns (T7.4): umlauts with or without the "e"."""

# The guard runs every pattern on the casefolded text with and without accents
# (guard.detection_views()), so "für" is also seen as "fur"; people who type without umlauts
# write "fuer". "ß" needs no rule: casefold() turns "ß" and "ẞ" into "ss", so patterns use "ss".
_UMLAUTS = {"ä": "(?:ä|ae|a)", "ö": "(?:ö|oe|o)", "ü": "(?:ü|ue|u)"}


def german(pattern: str) -> str:
    """Return the pattern with each umlaut also matching its plain and "e" spellings."""
    return "".join(_UMLAUTS.get(char, char) for char in pattern)
