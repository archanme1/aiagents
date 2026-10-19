import pytest

from database.db import create_user

CREDS = {"email": "jane@example.com", "password": "password123"}
ERROR = "Invalid email or password."


@pytest.fixture
def user_id():
    return create_user("Jane", CREDS["email"], CREDS["password"])


def test_get_login_renders_form(client):
    response = client.get("/login")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="email"' in html
    assert 'name="password"' in html


def test_valid_login_sets_session_and_redirects(client, user_id):
    response = client.post("/login", data=CREDS)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    with client.session_transaction() as s:
        assert s["user_id"] == user_id
        assert isinstance(s["user_id"], int)


def test_email_is_case_and_whitespace_insensitive(client, user_id):
    response = client.post(
        "/login", data={"email": "  JANE@Example.com ", "password": CREDS["password"]}
    )
    assert response.status_code == 302
    with client.session_transaction() as s:
        assert s["user_id"] == user_id


def test_wrong_password_shows_generic_error(client, user_id):
    response = client.post("/login", data={**CREDS, "password": "wrong-password"})
    assert response.status_code == 200
    assert ERROR in response.get_data(as_text=True)
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_unknown_email_shows_same_error(client, user_id):
    response = client.post("/login", data={**CREDS, "email": "nobody@example.com"})
    assert response.status_code == 200
    assert ERROR in response.get_data(as_text=True)
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_failed_login_refills_email_only(client, user_id):
    response = client.post("/login", data={**CREDS, "password": "wrong-password"})
    html = response.get_data(as_text=True)
    assert 'value="jane@example.com"' in html
    assert "wrong-password" not in html


def test_logout_clears_session_and_redirects(client, user_id):
    client.post("/login", data=CREDS)
    response = client.get("/logout")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    with client.session_transaction() as s:
        assert "user_id" not in s


def test_logout_when_logged_out_still_redirects(client):
    response = client.get("/logout")
    assert response.status_code == 302


def test_logout_no_longer_returns_stub(client):
    response = client.get("/logout")
    assert b"coming in Step 3" not in response.get_data()


def test_navbar_shows_sign_out_when_logged_in(client, user_id):
    client.post("/login", data=CREDS)
    html = client.get("/").get_data(as_text=True)
    assert "Sign out" in html
    assert "Get started" not in html


def test_navbar_shows_sign_in_when_logged_out(client):
    html = client.get("/").get_data(as_text=True)
    assert "Sign in" in html
    assert "Sign out" not in html


@pytest.mark.parametrize("path", ["/login", "/register"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_auth_pages_redirect_when_logged_in(client, user_id, path, method):
    client.post("/login", data=CREDS)
    response = getattr(client, method)(path)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
