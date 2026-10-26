"""Shared limits for new PayPal requests and issuance."""

MIN_PAYPAL_AMOUNT = 40
MAX_PAYPAL_AMOUNT = 100_000


def valid_paypal_request_amount(amount: object) -> bool:
    return type(amount) is int and MIN_PAYPAL_AMOUNT <= amount <= MAX_PAYPAL_AMOUNT
