import database.db as db


def test_login_valid_credentials_redirects_to_landing(client):
    response = client.post(
        "/login", data={"email": "demo@spendly.com", "password": "demo123"}
    )
    assert response.status_code == 302
    assert response.location == "/"


def test_login_valid_credentials_sets_session_user_id(client):
    with client:
        client.post(
            "/login", data={"email": "demo@spendly.com", "password": "demo123"}
        )
        user = db.get_user_by_email("demo@spendly.com")
        with client.session_transaction() as sess:
            assert sess["user_id"] == user["id"]


def test_login_wrong_password_shows_generic_error_and_no_session(client):
    with client:
        response = client.post(
            "/login", data={"email": "demo@spendly.com", "password": "wrongpass"}
        )
        assert response.status_code == 200
        assert b"Invalid email or password" in response.data
        with client.session_transaction() as sess:
            assert "user_id" not in sess


def test_login_nonexistent_email_shows_same_generic_error(client):
    response = client.post(
        "/login", data={"email": "nobody@example.com", "password": "whatever"}
    )
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_login_failed_attempt_repopulates_email_field(client):
    response = client.post(
        "/login", data={"email": "demo@spendly.com", "password": "wrongpass"}
    )
    assert b'value="demo@spendly.com"' in response.data
    assert b"wrongpass" not in response.data


def test_logout_clears_session_and_redirects_to_login(client):
    with client:
        client.post(
            "/login", data={"email": "demo@spendly.com", "password": "demo123"}
        )
        response = client.get("/logout")
        assert response.status_code == 302
        assert response.location == "/login"
        with client.session_transaction() as sess:
            assert "user_id" not in sess


def test_navbar_shows_logout_link_when_logged_in(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    response = client.get("/")
    assert b"Log out" in response.data
    assert b"Sign in" not in response.data


def test_navbar_shows_signin_and_getstarted_when_logged_out(client):
    response = client.get("/")
    assert b"Sign in" in response.data
    assert b"Get started" in response.data
    assert b"Log out" not in response.data


def test_navbar_reverts_after_logout(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    client.get("/logout")
    response = client.get("/")
    assert b"Sign in" in response.data
    assert b"Log out" not in response.data


def test_login_page_redirects_to_landing_when_already_logged_in(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    response = client.get("/login")
    assert response.status_code == 302
    assert response.location == "/"


def test_register_page_redirects_to_landing_when_already_logged_in(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    response = client.get("/register")
    assert response.status_code == 302
    assert response.location == "/"
