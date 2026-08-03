"""Fixed question-only refusal policy for protected Agent boundaries."""

from __future__ import annotations


_PROTECTIVE_FRAMES = (
    "avoid ",
    "do not ",
    "don't ",
    "prevent ",
    "protect against ",
)
_REFUSAL_INTENTS = (
    (
        ("reveal ", "expose ", "print "),
        (
            "hidden system instructions",
            "secret value",
            "hidden context",
            "identity mapping",
        ),
    ),
    (("ignore ", "bypass "), ("evidence boundaries", "authorization")),
    (("cite ", "use "), ("forbidden evidence",)),
    (("override ",), ("authorization", "evidence boundaries")),
    (("follow ", "execute "), ("untrusted tool directions",)),
)


def should_refuse_agent_question(question: object) -> bool:
    """Return a fixed decision without retaining or projecting question text."""

    if not isinstance(question, str):
        return False
    normalized = " ".join(question.casefold().split())
    if not normalized or any(frame in normalized for frame in _PROTECTIVE_FRAMES):
        return False
    return any(
        any(action in normalized for action in actions)
        and any(target in normalized for target in targets)
        for actions, targets in _REFUSAL_INTENTS
    )
