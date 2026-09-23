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
        "bio": user.bio,
        "gender": user.gender,
        "age": user.age,
        "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
    }
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
