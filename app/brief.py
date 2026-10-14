"""Creator briefs: free-text context plus declared topics with a moderation policy each."""

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


DEFAULT_BRIEF = Brief(
    name="Streameuse FR (défaut)",
    creator_context=(
        "Je suis une streameuse FR de 25 ans. Je viens de me séparer de mon copain, "
        "c'est public. Je suis en reprise sportive. La critique de mon gameplay est OK, "
        "même dure."
    ),
    topics=[
        Topic(
            key="breakup",
            label="Rupture",
            description="Any mention, mockery, speculation or 'advice' about my breakup or my ex",
            policy="remove",
        ),
        Topic(
            key="body",
            label="Corps / apparence",
            description="Comments on my body, weight, appearance, clothing, or sexualisation",
            policy="remove",
        ),
        Topic(
            key="gameplay",
            label="Gameplay",
            description="Criticism of my skill, decisions, rank",
            policy="tolerate",
        ),
        Topic(
            key="sponsors",
            label="Sponsors",
            description="Attacks on my brand deals or accusations of selling out",
            policy="hold",
        ),
    ],
)

EN_GAMER_BRIEF = Brief(
    name="EN gaming streamer",
    creator_context=(
        "I'm a 30-year-old UK variety streamer. Banter and trash talk are part of my chat "
        "culture, don't over-flag jokes. Criticism of my gameplay is fine, even harsh. "
        "I never discuss my family on stream."
    ),
    topics=[
        Topic(
            key="family",
            label="Family",
            description="Any mention of my family, partner or kids, including 'jokes' about them",
            policy="remove",
        ),
        Topic(
            key="politics",
            label="Politics bait",
            description="Attempts to bait me into political or culture-war arguments",
            policy="hold",
        ),
        Topic(
            key="gameplay",
            label="Gameplay",
            description="Criticism of my skill, game choices, rank",
            policy="tolerate",
        ),
        Topic(
            key="backseat",
            label="Backseating",
            description="Aggressive backseat gaming: repeated unsolicited orders about what I should do in game",
            policy="hold",
        ),
    ],
)

IG_FITNESS_BRIEF = Brief(
    name="Instagram fitness creator",
    creator_context=(
        "I'm a fitness creator posting workout and nutrition content. I've spoken openly "
        "about recovering from an eating disorder. Technical criticism of my form or "
        "programming is welcome."
    ),
    topics=[
        Topic(
            key="ed",
            label="Eating / weight",
            description=(
                "Comments about eating disorders, starvation, 'too skinny' or 'too big' "
                "remarks, diet-shaming or food policing"
            ),
            policy="remove",
        ),
        Topic(
            key="body",
            label="Sexualisation",
            description="Sexualising comments on my body, poses or clothing",
            policy="remove",
        ),
        Topic(
            key="pseudoscience",
            label="Pseudoscience claims",
            description="Accusations of promoting fake science, dangerous advice or scam supplements",
            policy="hold",
        ),
        Topic(
            key="form",
            label="Form / technique",
            description="Criticism of my exercise form, programming or technique",
            policy="tolerate",
        ),
    ],
)

PRESETS: dict[str, Brief] = {
    "fr_streamer": DEFAULT_BRIEF,
    "en_gamer": EN_GAMER_BRIEF,
    "ig_fitness": IG_FITNESS_BRIEF,
}
