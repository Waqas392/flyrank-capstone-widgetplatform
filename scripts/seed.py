"""Seed demo data (idempotent): python -m scripts.seed"""
from __future__ import annotations

import json

from app.config import Settings
from app.db import make_engine, make_session_factory, run_migrations, utcnow
from app.models import Widget
from app.repo import get_owner_by_email
from app.services import auth, security
from app.services import widgets as svc

EMAIL, PASSWORD = "demo@example.com", "demo-password-123"
DEMO = [
    ("demo-signup", "signup_form", "Join our newsletter", "Get one email a week. No spam.", "Subscribe"),
    ("demo-contact", "contact_form", "Contact us", "We reply within a day.", "Send message"),
    ("demo-popover", "cta_popover", "Early access", "Be first to try the beta.", "Get access"),
]


def main() -> None:
    settings = Settings.from_env()
    engine = make_engine(settings.database_url)
    run_migrations(engine)
    with make_session_factory(engine)() as s:
        owner = get_owner_by_email(s, EMAIL)
        if owner:
            _, token = auth.login(s, EMAIL, PASSWORD, settings.token_ttl_hours)
        else:
            owner, token = auth.register(s, EMAIL, PASSWORD, settings.token_ttl_hours)
        for wid, wtype, title, desc, button in DEMO:
            if s.get(Widget, wid):
                continue
            fields = svc.DEFAULT_FIELDS[wtype]
            now = utcnow()
            s.add(Widget(
                id=wid, owner_id=owner.id, type=wtype, title=title, description=desc, button_text=button,
                fields_json=json.dumps([f.model_dump() for f in fields]),
                display_json=json.dumps({"mode": "popover" if wtype == "cta_popover" else "inline",
                                         "delay_seconds": 3 if wtype == "cta_popover" else 0}),
                honeypot_field=svc.DEFAULT_HONEYPOT, is_active=True, version=1, created_at=now, updated_at=now,
            ))
        s.commit()
    print(f"Seeded owner {EMAIL} / {PASSWORD}")
    print(f"Bearer token (shown once, valid {settings.token_ttl_hours}h): {token}")
    for wid, *_ in DEMO:
        print(f'  <script src="{settings.public_base_url}/widget.js?id={wid}" async></script>')


if __name__ == "__main__":
    main()
