"""
Auth flow: register -> pending -> admin-code verify -> login -> (OTP) ->
protected route -> refresh -> logout. Also covers the rejection paths
(duplicate email, wrong password, unapproved login, bad/expired/reused
codes, bad refresh token).
"""
EMAIL = "a@example.com"
PASSWORD = "SecurePass123"


def _register(client, email=EMAIL, password=PASSWORD, name="A"):
    return client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": password},
    )


def _last_code(client, kind):
    return client.captured_codes[kind][-1][1]


def _register_and_approve(client, email=EMAIL, password=PASSWORD):
    _register(client, email, password)
    code = _last_code(client, "registration")
    client.post("/api/v1/auth/registration/verify", json={"email": email, "code": code})


def _login_to_tokens(client, email=EMAIL, password=PASSWORD):
    """Runs login, transparently completing the OTP step if required, and
    returns the final JSON body containing access_token/refresh_token."""
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    body = response.json()
    if response.status_code == 200 and body.get("status") == "otp_required":
        otp = _last_code(client, "login_otp")
        response = client.post(
            "/api/v1/auth/login/verify-otp", json={"email": email, "code": otp}
        )
        body = response.json()
    return response, body


# ---------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------


def test_register_creates_pending_account_and_emails_admin(client):
    response = _register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending_approval"

    assert len(client.captured_codes["registration"]) == 1
    emailed_to, code = client.captured_codes["registration"][0]
    assert emailed_to == EMAIL
    assert len(code) == 8


def test_register_duplicate_email_rejected(client):
    _register(client, email="dupe@example.com")
    response = _register(client, email="dupe@example.com")
    assert response.status_code == 409


def test_register_short_password_rejected(client):
    response = _register(client, email="short@example.com", password="short1")
    assert response.status_code == 422


# ---------------------------------------------------------------------
# Registration verification
# ---------------------------------------------------------------------


def test_registration_verify_with_correct_code_approves_account(client):
    _register(client)
    code = _last_code(client, "registration")

    response = client.post(
        "/api/v1/auth/registration/verify", json={"email": EMAIL, "code": code}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_registration_verify_does_not_return_tokens(client):
    _register(client)
    code = _last_code(client, "registration")
    response = client.post(
        "/api/v1/auth/registration/verify", json={"email": EMAIL, "code": code}
    )
    assert "access_token" not in response.json()


def test_registration_verify_wrong_code_rejected(client):
    _register(client)
    response = client.post(
        "/api/v1/auth/registration/verify", json={"email": EMAIL, "code": "WRONGCODE"}
    )
    assert response.status_code == 400


def test_registration_verify_code_is_single_use(client):
    _register(client)
    code = _last_code(client, "registration")
    first = client.post(
        "/api/v1/auth/registration/verify", json={"email": EMAIL, "code": code}
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/auth/registration/verify", json={"email": EMAIL, "code": code}
    )
    assert second.status_code == 400


def test_registration_resend_issues_new_code_and_invalidates_old(client):
    _register(client)
    old_code = _last_code(client, "registration")

    resend = client.post("/api/v1/auth/registration/resend", json={"email": EMAIL})
    assert resend.status_code == 200
    new_code = _last_code(client, "registration")
    assert new_code != old_code

    stale = client.post(
        "/api/v1/auth/registration/verify", json={"email": EMAIL, "code": old_code}
    )
    assert stale.status_code == 400

    fresh = client.post(
        "/api/v1/auth/registration/verify", json={"email": EMAIL, "code": new_code}
    )
    assert fresh.status_code == 200


# ---------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------


def test_login_before_approval_is_rejected(client):
    _register(client)
    response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 403
    assert response.json()["status"] == "pending_approval"


def test_login_wrong_password_rejected(client):
    _register_and_approve(client)
    response = client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": "WrongPassword1"}
    )
    assert response.status_code == 401


def test_login_after_approval_requires_otp_then_succeeds(client):
    _register_and_approve(client)
    first = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert first.status_code == 200
    assert first.json()["status"] == "otp_required"
    assert len(client.captured_codes["login_otp"]) == 1

    otp = _last_code(client, "login_otp")
    second = client.post(
        "/api/v1/auth/login/verify-otp", json={"email": EMAIL, "code": otp}
    )
    assert second.status_code == 200
    body = second.json()
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20
    assert len(body["refresh_token"]) > 20
    assert body["user"]["email"] == EMAIL


def test_login_otp_is_single_use(client):
    _register_and_approve(client)
    client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    otp = _last_code(client, "login_otp")

    first = client.post("/api/v1/auth/login/verify-otp", json={"email": EMAIL, "code": otp})
    assert first.status_code == 200
    second = client.post("/api/v1/auth/login/verify-otp", json={"email": EMAIL, "code": otp})
    assert second.status_code == 401


def test_registration_code_cannot_be_used_as_login_otp(client):
    _register(client)
    reg_code = _last_code(client, "registration")
    client.post("/api/v1/auth/registration/verify", json={"email": EMAIL, "code": reg_code})
    client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})

    response = client.post(
        "/api/v1/auth/login/verify-otp", json={"email": EMAIL, "code": reg_code}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------
# Protected routes
# ---------------------------------------------------------------------


def test_protected_route_requires_token(client):
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401


def test_protected_route_rejects_garbage_token(client):
    response = client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


def test_protected_route_with_valid_token(client):
    _register_and_approve(client)
    _, tokens = _login_to_tokens(client)
    response = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == EMAIL
    assert response.json()["is_approved"] is True


# ---------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------


def test_refresh_issues_new_tokens_and_rotates(client):
    _register_and_approve(client)
    _, tokens = _login_to_tokens(client)

    response = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # Old refresh token was rotated out and must no longer work.
    reused = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reused.status_code == 401

    # New access token works against a protected route.
    me = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {new_tokens['access_token']}"}
    )
    assert me.status_code == 200


def test_refresh_rejects_garbage_token(client):
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert response.status_code == 401


# ---------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------


def test_logout_revokes_refresh_token(client):
    _register_and_approve(client)
    _, tokens = _login_to_tokens(client)

    logout = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert logout.status_code == 200

    reused = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reused.status_code == 401


def test_logout_requires_bearer_token(client):
    response = client.post("/api/v1/auth/logout", json={"refresh_token": "whatever"})
    assert response.status_code == 401
