def test_profile_redirects_when_not_logged_in(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.location == "/login"


def test_profile_shows_real_seed_user_data(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    response = client.get("/profile")
    assert response.status_code == 200
    assert b"Demo User" in response.data
    assert b"demo@spendly.com" in response.data
    assert "₹".encode() in response.data
    assert "288.94".encode() in response.data
    assert b">8<" in response.data
    assert b"Bills" in response.data


def test_profile_new_user_shows_zero_state(client):
    client.post(
        "/register",
        data={
            "name": "New Person",
            "email": "newperson@example.com",
            "password": "secret123",
            "confirm_password": "secret123",
        },
    )
    client.post("/login", data={"email": "newperson@example.com", "password": "secret123"})
    response = client.get("/profile")
    assert response.status_code == 200
    assert "0.00".encode() in response.data
    assert "—".encode() in response.data
