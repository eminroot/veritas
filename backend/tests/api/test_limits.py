"""Request bodies are small, except files on the routes that take them, and a body over its
limit gets the API's JSON error before anything parses it."""

from support import error


def test_a_json_body_larger_than_any_request_needs_is_refused_unread(client):
    body = b"[" + b"[]," * 700_000 + b"[]]"  # about 2 MB: twice what any JSON request needs
    response = client.post(
        "/v1/capture-sessions/00000000-0000-4000-8000-000000000000/manifest",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    error(response, 413, "payload_too_large")
    assert response.headers["content-type"] == "application/json"


def test_a_streamed_body_over_the_limit_is_refused_in_the_same_format(client):
    def chunks():
        for _ in range(40):
            yield b"x" * 65_536

    response = client.post(
        "/v1/auth/otp", content=chunks(), headers={"Content-Type": "application/json"}
    )
    error(response, 413, "payload_too_large")


def test_a_file_too_large_for_the_upload_route_is_refused_in_the_api_format(client, settings):
    big = b"\0" * (settings.max_upload_bytes + 2 * 1024 * 1024)
    response = client.post(
        "/v1/capture-sessions/00000000-0000-4000-8000-000000000000/items",
        files={"file": ("big.pdf", big, "application/pdf")},
    )
    error(response, 413, "payload_too_large")


def test_a_multipart_type_in_capitals_is_still_a_file_upload(client):
    """Media types are case-insensitive; a file route takes a file whatever the case."""
    boundary = "VeritasBoundary"
    head = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()
    body = head + b"%PDF-" + bytes(2 * 1024 * 1024) + f"\r\n--{boundary}--\r\n".encode()
    response = client.post(
        "/v1/capture-sessions/00000000-0000-4000-8000-000000000000/items",
        content=body,
        headers={"Content-Type": f"Multipart/Form-Data; boundary={boundary}"},
    )
    assert response.status_code != 413, response.text
