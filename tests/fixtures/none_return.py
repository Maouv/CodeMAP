def get_user(uid: int) -> "User | None":
    return None


def caller():
    u = get_user(1)
    return u.name  # unchecked
