from types import SimpleNamespace

from fastapi.testclient import TestClient

import auth
import main


def test_login_uses_customer_from_database(monkeypatch):
    customer = {
        "customer_id": 42,
        "first_name": "Mira",
        "last_name": "Rao",
        "email": "mira@example.test",
        "home_location": "Pune",
        "home_country": "India",
        "joined_at": None,
        "pin_hash": auth.hash_pin("4826"),
    }
    monkeypatch.setattr(
        main,
        "db",
        SimpleNamespace(get_customer_by_email=lambda email: customer),
        raising=False,
    )

    response = TestClient(main.app).post(
        "/login", json={"email": "mira@example.test", "pin": "4826"}
    )

    assert response.status_code == 200
    assert response.json()["customer_id"] == 42
