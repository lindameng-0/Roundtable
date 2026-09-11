"""Owner privileges derive only from the authenticated, verified database user."""
import os


def is_owner(user: dict) -> bool:
    email = os.environ.get("OWNER_EMAIL", "itsyuko0o1@gmail.com").strip().casefold()
    pinned_id = os.environ.get("OWNER_USER_ID", "").strip()
    return bool(email and user.get("email_verified") is True
                and str(user.get("email", "")).strip().casefold() == email
                and (not pinned_id or user.get("user_id") == pinned_id))
