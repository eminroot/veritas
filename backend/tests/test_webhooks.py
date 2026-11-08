import pytest

from veritas.payments.webhooks import WebhookError, sign, verify

SECRET = b"whsec_test_secret"
BODY = b'{"type":"payment.succeeded","data":{"id":"pay_1","amount":1250}}'
NOW = 1_800_000_000


def test_round_trip():
    header = sign(SECRET, BODY, NOW)
    assert verify(SECRET, header, BODY, NOW + 10) == NOW


@pytest.mark.parametrize(
    ("header", "body", "now"),
    [
        (None, BODY, NOW),
        ("", BODY, NOW),
        ("v1=abc", BODY, NOW),
        (sign(SECRET, BODY, NOW), BODY + b" ", NOW),
        (sign(b"other secret", BODY, NOW), BODY, NOW),
        (sign(SECRET, BODY, NOW), BODY, NOW + 301),
        (sign(SECRET, BODY, NOW + 400), BODY, NOW),
        ("t=notanumber,v1=00", BODY, NOW),
    ],
    ids=[
        "missing",
        "empty",
        "no timestamp",
        "body changed",
        "wrong secret",
        "too old",
        "from the future",
        "bad timestamp",
    ],
)
def test_refuses(header, body, now):
    with pytest.raises(WebhookError):
        verify(SECRET, header, body, now)


def test_any_listed_signature_may_match():
    good = sign(SECRET, BODY, NOW).split("v1=")[1]
    header = f"t={NOW},v1=deadbeef,v1={good}"
    assert verify(SECRET, header, BODY, NOW) == NOW
