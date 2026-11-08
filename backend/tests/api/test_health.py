from support import error, ok


def test_liveness(client):
    assert ok(client.get("/health")) == {"status": "ok"}


def test_readiness_checks_the_database_and_postgis(client):
    body = ok(client.get("/health/ready"))
    assert body["status"] == "ready"
    assert body["postgis"].startswith("3.")


def test_unknown_address_uses_the_error_format(client):
    body = error(client.get("/v1/nothing-here"), 404, "not_found")
    assert body == {
        "code": "not_found",
        "message": "There is nothing at this address.",
        "details": [],
    }


def test_wrong_method(client):
    error(client.delete("/health"), 405, "method_not_allowed")


def test_invalid_input_lists_each_field(client):
    response = client.post("/v1/auth/otp", json={"phone": "12345", "extra": 1})
    body = error(response, 422, "invalid_request")
    assert body["message"] == "Some fields are missing or not valid."
    assert {"path": "body.extra", "message": "is not a known field, remove it"} in body["details"]
    [phone] = [detail for detail in body["details"] if detail["path"] == "body.phone"]
    assert "not an Azerbaijani phone number" in phone["message"]


def test_missing_body_and_broken_json(client):
    body = error(client.post("/v1/auth/otp"), 422, "invalid_request")
    assert body["details"] == [{"path": "body", "message": "is required"}]
    response = client.post(
        "/v1/auth/otp", content=b'{"phone": ', headers={"Content-Type": "application/json"}
    )
    body = error(response, 422, "invalid_request")
    assert body["details"] == [{"path": "body", "message": "is not valid JSON"}]


def test_protected_endpoints_need_a_token(client):
    response = client.get("/v1/me")
    error(response, 401, "not_authenticated")
    assert response.headers["WWW-Authenticate"] == "Bearer"
    response = client.get("/v1/me", headers={"Authorization": "Bearer not-a-real-token"})
    error(response, 401, "not_authenticated")


def test_openapi_has_tags_and_our_error_format(client):
    spec = ok(client.get("/openapi.json"))
    assert {"auth", "charities", "contractors", "officers", "projects"} <= {
        tag["name"] for tag in spec["tags"]
    }
    assert "ErrorResponse" in spec["components"]["schemas"]
    assert "HTTPValidationError" not in spec["components"]["schemas"]
