import requests
from django.conf import settings

RAZORPAY_BASE = "https://api.razorpay.com/v1"


def _auth():
    return (settings.PLATFORM_RAZORPAY_KEY_ID, settings.PLATFORM_RAZORPAY_KEY_SECRET)


def create_plan(*, period, interval, item_name, amount_paise, currency="INR"):
    """POST /v1/plans — creates a Plan on Razorpay's side (their Plan, not ours)."""
    resp = requests.post(
        f"{RAZORPAY_BASE}/plans",
        json={
            "period": period,
            "interval": interval,
            "item": {"name": item_name, "amount": amount_paise, "currency": currency},
        },
        auth=_auth(),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def create_subscription(*, razorpay_plan_id, total_count, notes=None):
    """POST /v1/subscriptions — creates a Subscription awaiting authentication payment."""
    resp = requests.post(
        f"{RAZORPAY_BASE}/subscriptions",
        json={
            "plan_id": razorpay_plan_id,
            "total_count": total_count,
            "notes": notes or {},
        },
        auth=_auth(),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()