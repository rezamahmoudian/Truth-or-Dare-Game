from apps.users.models import Friendship, User


def person_payload(user: User, *, relation: str | None = None) -> dict:
    """A user as other people see them.

    Note what is absent: birth_date. Only the derived age leaves the server —
    the exact date is an identifier and nobody else needs it.
    """
    payload = {
        "id": user.pk,
        "username": user.username,
        "display_name": user.display_name,
        "avatar": user.avatar,
        "avatar_url": user.avatar_url,
        "bio": user.bio,
        "city": user.city,
        "interests": user.interests,
        "gender": user.gender,
        "age": user.age,
        "is_ai": user.is_ai,
        "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
    }
    if user.is_ai and hasattr(user, "ai_persona"):
        payload["ai_profile"] = user.ai_persona.public_profile()
        payload["age"] = user.ai_persona.age
    if relation is not None:
        payload["relation"] = relation
    return payload


def request_payload(friendship: Friendship, *, direction: str) -> dict:
    other = friendship.to_user if direction == "outgoing" else friendship.from_user
    return {
        "id": friendship.pk,
        "direction": direction,
        "user": person_payload(other),
        "created_at": friendship.created_at.isoformat(),
    }
