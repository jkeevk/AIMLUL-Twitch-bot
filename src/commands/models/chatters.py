from dataclasses import dataclass


@dataclass
class ChatterData:
    """
    Represents a Twitch chat user (chatter) with basic identification info.

    Attributes:
        id: The unique Twitch user ID.
        name: The login name of the user (lowercase).
        display_name: The display name of the user (may include uppercase letters).
    """

    id: str
    name: str
    display_name: str
