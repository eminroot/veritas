"""Test data and small helpers for the API tests.

The organisations match docs/examples/passport.example.json, so the example
Passport can be published as it is.
"""

PDF = b"%PDF-1.7\n%Veritas test document\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(32)

CHARITY = {
    "legal_name": "Bərəkət İctimai Birliyi",
    "voen": "1700000011",
    "legal_form": "Public union",
    "legal_address": "Bakı, Nizami küçəsi 10",
    "director_name": "Leyla Məmmədova",
    "contact_email": "info@bereket.example.az",
    "contact_phone": "(012) 345 67 89",
    "website": "https://bereket.example.az",
}

CONTRACTOR = {
    "legal_name": "Dağ Tikinti MMC",
    "voen": "1300000021",
    "iban": "AZ21 NABZ 0000 0000 1370 1000 1944",
    "legal_address": "Qəbələ rayonu, Yeni Qala kəndi",
    "director_name": "Rauf Həsənov",
}

OFFICER = {
    "name": "Nərmin Əliyeva",
    "organisation": "Sample Audit Partners",
    "address": "0x15d34aaf54267db7d7c367839aaf71a00a2c6a65",
}


def upload(
    client,
    url,
    person,
    *,
    data=PDF,
    content_type="application/pdf",
    kind="registration",
    filename="registration.pdf",
):
    return client.post(
        url,
        data={"kind": kind},
        files={"file": (filename, data, content_type)},
        headers=person.headers,
    )


def ok(response, status=200):
    """The JSON body, after checking the status. Shows the body when it is wrong."""
    assert response.status_code == status, response.text
    return response.json()


def error(response, status, code):
    """The error body, after checking the status and the error code."""
    assert response.status_code == status, response.text
    body = response.json()["error"]
    assert body["code"] == code, body
    return body
