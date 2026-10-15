"""Creator briefs: free-text context plus declared topics with a moderation policy each.

Each source (twitch, instagram) has its own independent brief. The defaults are
deliberately generic one-liners — add topics and context from the UI.
"""

from typing import Literal

from pydantic import BaseModel

Policy = Literal["remove", "hold", "tolerate"]


class Topic(BaseModel):
    key: str
    label: str
    description: str
    policy: Policy = "remove"


class Brief(BaseModel):
    name: str
    creator_context: str
    topics: list[Topic]


DEFAULT_BRIEFS: dict[str, Brief] = {
    "twitch": Brief(
        name="Twitch",
        creator_context=(
            "Je suis créateur·rice et je streame sur Twitch : signale ce qui est "
            "hostile ou toxique envers moi dans le chat."
        ),
        topics=[],
    ),
    "instagram": Brief(
        name="Instagram",
        creator_context=(
            "Je suis créateur·rice et je poste sur Instagram : signale ce qui est "
            "hostile ou toxique envers moi dans les commentaires."
        ),
        topics=[],
    ),
}
