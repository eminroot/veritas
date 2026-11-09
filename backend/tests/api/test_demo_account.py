"""The demo account the judges sign in with: scripts/seed_demo.py makes it, and puts it back."""

import importlib.util
from pathlib import Path

from sqlalchemy import func, select, text, update
from support import error, ok

from veritas.db.models import User

SCRIPT = Path(__file__).parents[2] / "scripts" / "seed_demo.py"


def load_script():
    spec = importlib.util.spec_from_file_location("seed_demo", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def log_in(client, password="admin1234"):
    return client.post("/v1/auth/login", json={"email": "admin@gmail.com", "password": password})


def test_the_demo_account_signs_in_with_the_published_credentials(client, db):
    load_script().seed_demo(db)
    db.commit()
    user = ok(log_in(client))["user"]
    assert user["email"] == "admin@gmail.com"
    assert user["display_name"] == "Demo Account"
    assert user["has_password"] is True
    assert user["is_admin"] is False


def test_seeding_again_puts_the_account_back(client, db):
    script = load_script()
    made = script.seed_demo(db)
    db.commit()

    # Someone changes the password, then locks the account with wrong guesses.
    token = ok(log_in(client))["access_token"]
    body = {"current_password": "admin1234", "new_password": "changed it 99"}
    changed = client.post(
        "/v1/me/password", json=body, headers={"Authorization": f"Bearer {token}"}
    )
    assert changed.status_code == 204, changed.text
    locked_until = func.now() + text("interval '1 hour'")
    db.execute(update(User).values(password_failures=7, password_locked_until=locked_until))
    db.commit()
    error(log_in(client), 429, "login_locked")

    again = script.seed_demo(db)
    db.commit()
    assert again.id == made.id
    ok(log_in(client))
    assert db.scalar(select(func.count()).select_from(User)) == 1
