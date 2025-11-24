def pluralize(count: int, word: str, case: str = "nominative") -> str:
    """
    Inflect Russian words based on count and grammatical case.

    Supports: победа, поражение, секунда, минута, час, игрок.
    Cases: 'nominative' (именительный), 'accusative' (винительный).

    Args:
        count: Number to determine plural form
        word: Base word to inflect
        case: Grammatical case ('nominative' or 'accusative')

    Returns:
        Properly inflected word form based on count and case
    """
    forms: dict[str, dict[str, tuple[str, str, str]]] = {
        "победа": {
            "nominative": ("победа", "победы", "побед"),
            "accusative": ("победу", "победы", "побед"),
        },
        "поражение": {
            "nominative": ("поражение", "поражения", "поражений"),
            "accusative": ("поражение", "поражения", "поражений"),
        },
        "секунда": {
            "nominative": ("секунда", "секунды", "секунд"),
            "accusative": ("секунду", "секунды", "секунд"),
        },
        "минута": {
            "nominative": ("минута", "минуты", "минут"),
            "accusative": ("минуту", "минуты", "минут"),
        },
        "час": {
            "nominative": ("час", "часа", "часов"),
            "accusative": ("час", "часа", "часов"),
        },
        "игрок": {
            "nominative": ("игрок", "игрока", "игроков"),
            "accusative": ("игрока", "игрока", "игроков"),
        },
    }

    if word not in forms or case not in forms[word]:
        return word

    word_forms = forms[word][case]

    last_digit = count % 10
    last_two_digits = count % 100

    if last_digit == 1 and last_two_digits != 11:
        return word_forms[0]
    elif 2 <= last_digit <= 4 and not (12 <= last_two_digits <= 14):
        return word_forms[1]
    else:
        return word_forms[2]


def format_duration(seconds: int) -> str:
    """
    Format duration into human-readable Russian string with proper inflection.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted duration string with correctly inflected time units
    """
    parts = []

    hours, seconds = divmod(seconds, 3600)
    if hours:
        parts.append(f"{hours} {pluralize(hours, 'час', case='accusative')}")

    minutes, seconds = divmod(seconds, 60)
    if minutes:
        parts.append(f"{minutes} {pluralize(minutes, 'минута', case='accusative')}")

    if seconds or not parts:
        parts.append(f"{seconds} {pluralize(seconds, 'секунда', case='accusative')}")

    return " ".join(parts)
