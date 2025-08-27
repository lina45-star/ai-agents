from fastapi import FastAPI, HTTPException
from typing import Optional

app = FastAPI(title="Yovite Core Mock", version="0.2.0")

# --- Orders
ORDERS = {
    # <=14 Tage, bezahlt -> REFUND_ALLOWED_14D
    "4711": {
        "order_id": "4711",
        "buyer_email": "kunde@example.com",
        "created_at": "2025-08-20",
        "total_amount": 50.0,
        "currency": "EUR",
        "payment_status": "PAID",
        "paid_at": "2025-08-20",
        "refund_status": "NONE",
    },
    # >14 Tage, bezahlt -> REFUND_DENIED_TIMEOUT
    "9001": {
        "order_id": "9001",
        "buyer_email": "x@ex.de",
        "created_at": "2025-08-01",
        "total_amount": 80.0,
        "currency": "EUR",
        "payment_status": "PAID",
        "paid_at": "2025-08-01",
        "refund_status": "NONE",
    },
    # unbezahlt -> CANCEL_NO_PAYMENT
    "7777": {
        "order_id": "7777",
        "buyer_email": "nopay@example.com",
        "created_at": "2025-08-25",
        "total_amount": 30.0,
        "currency": "EUR",
        "payment_status": "PENDING",
        "refund_status": "NONE",
    },
}

# --- Vouchers
VOUCHERS = {
    # Universal, nicht eingelöst -> INSTRUCT_REDEEM_ONLINE
    ("ABC123", "9999"): {
        "voucher_code": "ABC123",
        "pin": "9999",
        "type": "universal",
        "issue_date": "2024-01-02",
        "valid_until": "2027-12-31",
        "status": "NOT_REDEEMED",
        "remaining_value": 50.0,
        "bound_restaurant_id": None,
        "redeemed_at": None,
    },
    # Restaurant-gebunden, bereits eingelöst -> REDEEM path, zeigt restaurant case; Cancel -> REFUND_DENIED_REDEEMED
    ("XYZ789", "1111"): {
        "voucher_code": "XYZ789",
        "pin": "1111",
        "type": "restaurant",
        "issue_date": "2023-09-01",
        "valid_until": "2026-12-31",
        "status": "REDEEMED",
        "remaining_value": 0.0,
        "bound_restaurant_id": "R1",
        "redeemed_at": "2025-08-15",
    },
    # Abgelaufen -> EXPIRED_NOT_REDEEMABLE (GENERAL)
    ("OLD000", "0000"): {
        "voucher_code": "OLD000",
        "pin": "0000",
        "type": "universal",
        "issue_date": "2020-05-01",
        "valid_until": "2023-12-31",
        "status": "EXPIRED",
        "remaining_value": 0.0,
        "bound_restaurant_id": None,
        "redeemed_at": None,
    },
}

DISPATCH = {
    "4711": {
        "order_id": "4711",
        "method": "email",
        "sent_at": "2025-08-20T10:00:00Z",
        "recipient_email": "kunde@example.com",
        "bounce_flag": False,
    }
}

RESTAURANTS = {
    "R1": {
        "id": "R1",
        "name": "Ristorante Demo",
        "city": "Hamburg",
        "is_active": True,
        "is_temporarily_closed": False,
    }
}

@app.get("/core/v1/order")
def get_order(order_id: Optional[str] = None, email: Optional[str] = None):
    if order_id and order_id in ORDERS:
        return ORDERS[order_id]
    if email:
        for o in ORDERS.values():
            if o["buyer_email"] == email:
                return o
    return {}

@app.get("/core/v1/voucher")
def get_voucher(code: str, pin: Optional[str] = None):
    key = (code, pin or "")
    if key in VOUCHERS:
        return VOUCHERS[key]
    # allow lookup just by code (e.g. missing PIN)
    for (c, p), v in VOUCHERS.items():
        if c == code and (pin is None or p == pin):
            return v
    raise HTTPException(status_code=404, detail="voucher not found")

@app.get("/core/v1/dispatch")
def get_dispatch(order_id: str):
    return DISPATCH.get(order_id, {})

@app.get("/core/v1/restaurant")
def get_restaurant(id: str):
    return RESTAURANTS.get(id, {})