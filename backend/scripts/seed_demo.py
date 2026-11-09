"""Make the demo account the judges sign in with, or put it back the way it was.

    cd backend
    uv run python scripts/seed_demo.py                # admin@gmail.com, password admin1234
    uv run python scripts/seed_demo.py --email someone@example.com --password "..."

It reads VERITAS_DATABASE_URL (or backend/.env) like the API, so run it against the database
the site uses, after `uv run alembic upgrade head`. Running it again sets the password back
and clears any lock left by wrong passwords, so the published credentials keep working.

It is an ordinary donor account. Until an account has donations of its own, the web app
shows it the same sample portfolio as every other account, so the dashboard has something
to show at every stage: money raised, in escrow, released, and refunded.
"""

from __future__ import annotations

import argparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from veritas.db.models import User
from veritas.db.session import make_engine, make_session_factory, session_scope
from veritas.services import passwords
from veritas.settings import get_settings

DEMO_EMAIL = "admin@gmail.com"
DEMO_PASSWORD = "admin1234"
DEMO_NAME = "Demo Account"


def seed_demo(
    session: Session, email: str = DEMO_EMAIL, password: str = DEMO_PASSWORD, name: str = DEMO_NAME
) -> User:
    """The demo account, made or reset: this email, this password, no lock."""
    email = email.strip().lower()
    password = passwords.check_new(password)
    user = session.scalars(select(User).where(User.email == email)).first()
    if user is None:
        user = User(email=email, display_name=name)
        session.add(user)
    elif user.display_name is None:
        user.display_name = name
    user.password_hash = passwords.hash_password(password)
    user.password_failures = 0
    user.password_locked_until = None
    session.flush()
    return user


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", default=DEMO_EMAIL)
    parser.add_argument("--password", default=DEMO_PASSWORD)
    parser.add_argument("--name", default=DEMO_NAME)
    options = parser.parse_args()
    engine = make_engine(get_settings().database_url)
    try:
        for session in session_scope(make_session_factory(engine)):
            user = seed_demo(session, options.email, options.password, options.name)
            print(f"Demo account ready: {user.email} (id {user.id})")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
