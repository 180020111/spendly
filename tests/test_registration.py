import database.db as db


def test_get_register_renders_form(client):
    response = client.get("/register")
    assert response.status_code == 200
    assert b"Create your account" in response.data


def test_register_valid_creates_user_with_hashed_password(client):
    response = client.post(
        "/register",
        data={
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "password": "secret123",
            "confirm_password": "secret123",
        },
    )
    assert response.status_code == 302
    assert response.location == "/login?registered=1"

    user = db.get_user_by_email("ada@example.com")
    assert user is not None
    assert user["password_hash"] != "secret123"
    assert user["password_hash"].startswith(("pbkdf2:", "scrypt:"))


def test_register_duplicate_email_shows_error_and_no_duplicate_row(client):
    data = {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "password": "secret123",
        "confirm_password": "secret123",
    }
    client.post("/register", data=data)

    response = client.post(
        "/register",
        data={
            "name": "Someone Else",
            "email": "ada@example.com",
            "password": "other123",
            "confirm_password": "other123",
        },
    )
    assert response.status_code == 200
    assert b"already exists" in response.data

    conn = db.get_db()
    try:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE email = ?", ("ada@example.com",)
        ).fetchone()["n"]
    finally:
        conn.close()
    assert count == 1


def test_register_missing_field_shows_error_no_crash(client):
    response = client.post(
        "/register",
        data={
            "email": "nobody@example.com",
            "password": "secret123",
            "confirm_password": "secret123",
        },
    )
    assert response.status_code == 200
    assert b"required" in response.data
    assert db.get_user_by_email("nobody@example.com") is None


def test_register_password_mismatch_shows_error_no_row(client):
    response = client.post(
        "/register",
        data={
            "name": "Grace Hopper",
            "email": "grace@example.com",
            "password": "secret123",
            "confirm_password": "different456",
        },
    )
    assert response.status_code == 200
    assert b"do not match" in response.data
    assert db.get_user_by_email("grace@example.com") is None


def test_login_get_with_registered_param_shows_success_message(client):
    response = client.get("/login?registered=1")
    assert response.status_code == 200
    assert b"auth-success" in response.data
    assert b"Account created successfully" in response.data


def test_login_get_without_registered_param_shows_no_success_message(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"auth-success" not in response.data
