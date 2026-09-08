"""Paddle Billing integration; all entitlements come from verified server events."""
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

import config as cfg
from routers.auth import _get_session_user
from services import credits
from services.billing_catalog import CATALOG, LEGACY_CATALOG
from services.rate_limit import enforce_rate_limit

billing_router = APIRouter(prefix="/api/billing")


class PaddleError(HTTPException):
    def __init__(self, provider_status):
        self.provider_status = provider_status
        super().__init__(502, "The payment service could not complete this request. Please retry.")



def environment():
    return os.environ.get("PADDLE_ENVIRONMENT", "sandbox")


def enabled():
    env = environment()
    token = os.environ.get("PADDLE_CLIENT_TOKEN", "")
    return bool(os.environ.get("PADDLE_API_KEY") and os.environ.get("PADDLE_WEBHOOK_SECRET")
                and ((env == "sandbox" and token.startswith("test_")) or
                     (env == "production" and token.startswith("live_") and os.environ.get("PADDLE_LIVE_ENABLED") == "true")))


async def paddle(method, path, data=None):
    if not enabled():
        raise HTTPException(503, "Payments are not available yet. Please try again later.")
    base = "https://sandbox-api.paddle.com" if environment() == "sandbox" else "https://api.paddle.com"
    async with httpx.AsyncClient(timeout=25) as client:
        response = await client.request(method, f"{base}/{path}",
            json=data if method != "GET" else None, params=data if method == "GET" else None,
            headers={"Authorization": f"Bearer {os.environ['PADDLE_API_KEY']}", "Paddle-Version": "1"})
    if response.status_code >= 400:
        # Do not leak provider response bodies or credentials to the browser.
        raise PaddleError(response.status_code)
    result = response.json()
    if isinstance(result.get("data"), list) and result.get("meta", {}).get("pagination", {}).get("has_more"):
        raise HTTPException(503, "Billing history requires reconciliation. Please contact support.")
    return result["data"]


def timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() if value else 0


async def wallet(user_id):
    await credits.ensure_wallet(user_id)
    return (await cfg.db.credit_wallets.find_one({"id": user_id}))["data"]


@billing_router.get("/catalog")
async def catalog():
    return {"catalog_version": 2, "starter_credits": cfg.STARTER_CREDITS, "payments_enabled": enabled(),
            "rollover_policy": "One paid billing cycle, capped at the new monthly allowance. Rollover is used first.",
            "provider": "paddle", "environment": environment(),
            "client_token": os.environ.get("PADDLE_CLIENT_TOKEN", "") if enabled() else "",
            "items": [{"id": key, **{k: v for k, v in item.items() if k != "env"},
                       "available": enabled() and bool(os.environ.get(item["env"]))}
                      for key, item in CATALOG.items()]}


@billing_router.get("/balance")
async def get_balance(request: Request):
    user = await _get_session_user(request)
    result = await credits.balance(user["user_id"])
    state = await wallet(user["user_id"])
    result.update(pending_checkout=bool(state.get("checkout_pending")), next_plan=state.get("next_plan"))
    rows = await cfg.db.credit_entries.find({"user_id": user["user_id"]}).sort("created_at", -1).to_list(50)
    result["history"] = [{**row["data"], "created_at": row["created_at"]} for row in rows
                         if row["data"].get("kind") in {"starter", "monthly", "topup", "usage", "release", "refund", "adjustment"}]
    return result


class CheckoutRequest(BaseModel):
    item: str


async def customer_for(user):
    uid = user["user_id"]
    state = await wallet(uid)
    if state.get("customer"):
        return state["customer"]
    customers = await paddle("GET", "customers", {"email": user["email"], "per_page": 200})
    existing = next((c for c in customers if c["email"].lower() == user["email"].lower()), None)
    if existing:
        # Do not attach a Paddle customer already owned by another account.
        owner = (existing.get("custom_data") or {}).get("roundtable_user_id")
        if owner != uid:
            raise HTTPException(409, "This billing email needs support review before it can be linked.")
        customer = existing
    else:
        customer = await paddle("POST", "customers", {"email": user["email"], "name": user.get("name"),
                                                     "custom_data": {"roundtable_user_id": uid}})
    def save(state):
        state.setdefault("customer", customer["id"])
        return {"kind": "customer", "customer": state["customer"]}
    return (await credits.change(uid, "paddle_customer", save))["customer"]


async def validated_price(item):
    price_id = os.environ.get(item["env"], "")
    if not price_id:
        raise HTTPException(503, "This plan is not available yet")
    price = await paddle("GET", f"prices/{price_id}")
    cycle = price.get("billing_cycle") or {}
    if (price.get("status") != "active" or price.get("unit_price", {}).get("currency_code") != "USD"
        or price.get("unit_price", {}).get("amount") != str(item["cents"])
        or price.get("trial_period")
        or (item["mode"] == "subscription" and cycle != {"interval": "month", "frequency": 1})
        or (item["mode"] == "payment" and cycle)):
        raise HTTPException(503, "Pricing configuration needs attention. Please contact support.")
    return price_id


async def pending_transaction(uid, customer):
    state = await wallet(uid)
    pending = state.get("checkout_pending")
    if not pending:
        return None
    if pending.get("transaction_id"):
        return await paddle("GET", f"transactions/{pending['transaction_id']}")
    # Recover a POST whose response was lost; never blindly create another sale.
    transactions = await paddle("GET", "transactions", {"customer_id": customer, "per_page": 200})
    return next((t for t in transactions if (t.get("custom_data") or {}).get("order_id") == pending["id"]), None)


async def clear_pending(uid, order_id, key):
    def clear(state):
        if (state.get("checkout_pending") or {}).get("id") == order_id:
            state.pop("checkout_pending", None)
        return {"kind": "checkout_closed"}
    await credits.change(uid, key, clear)


@billing_router.post("/checkout")
async def checkout(body: CheckoutRequest, request: Request):
    user = await _get_session_user(request)
    uid = user["user_id"]
    await enforce_rate_limit(request, "checkout", 20, 3600, identity=uid)
    item = CATALOG.get(body.item)
    if not item:
        raise HTTPException(400, "Unknown plan or credit pack")
    price_id = await validated_price(item)
    customer = await customer_for(user)
    state = await wallet(uid)
    pending = state.get("checkout_pending")
    if pending:
        transaction = await pending_transaction(uid, customer)
        if transaction and transaction["status"] in {"draft", "ready", "past_due"}:
            if pending["item"] != body.item:
                raise HTTPException(409, "Cancel your pending checkout before choosing another plan or pack.")
            return {"transaction_id": transaction["id"]}
        if not transaction or transaction["status"] not in {"completed", "canceled"}:
            raise HTTPException(409, "Your previous checkout is still processing. Refresh shortly or contact support.")
        if transaction["status"] == "completed":
            await fulfill_transaction(transaction)
        await clear_pending(uid, pending["id"], f"checkout_close:{transaction['id']}")
    if item["mode"] == "subscription":
        subs = await paddle("GET", "subscriptions", {"customer_id": customer, "per_page": 200})
        if any(s["status"] != "canceled" for s in subs):
            raise HTTPException(409, "You already have a subscription. Change your plan from the billing page.")
    order_id = str(uuid.uuid4())
    def claim(state):
        if state.get("checkout_pending"):
            raise HTTPException(409, "Another checkout is opening. Please refresh shortly.")
        state["checkout_pending"] = {"id": order_id, "item": body.item, "created": time.time()}
        return {"kind": "checkout_started", "item": body.item}
    await credits.change(uid, f"checkout:{order_id}", claim)
    try:
        transaction = await paddle("POST", "transactions", {"collection_mode": "automatic", "customer_id": customer,
            "items": [{"price_id": price_id, "quantity": 1}], "currency_code": "USD",
            "custom_data": {"roundtable_user_id": uid, "order_id": order_id, "item": body.item}})
    except PaddleError as exc:
        if 400 <= exc.provider_status < 500 and exc.provider_status != 408:
            await clear_pending(uid, order_id, f"checkout_rejected:{order_id}")
        raise
    except (httpx.ConnectError, httpx.ConnectTimeout):
        await clear_pending(uid, order_id, f"checkout_unconnected:{order_id}")
        raise HTTPException(502, "Could not connect to the payment service. Please retry.")
    def save(state):
        if (state.get("checkout_pending") or {}).get("id") == order_id:
            state["checkout_pending"]["transaction_id"] = transaction["id"]
        return {"kind": "checkout_ready", "transaction_id": transaction["id"]}
    await credits.change(uid, f"checkout_ready:{order_id}", save)
    return {"transaction_id": transaction["id"]}


@billing_router.post("/checkout/cancel")
async def cancel_checkout(request: Request):
    user = await _get_session_user(request)
    uid = user["user_id"]
    state = await wallet(uid)
    pending = state.get("checkout_pending")
    if not pending:
        return {"cancelled": True}
    transaction = await pending_transaction(uid, state["customer"])
    if not transaction:
        raise HTTPException(409, "Checkout creation is still being reconciled. Please contact support.")
    if transaction["status"] == "completed":
        await fulfill_transaction(transaction)
        raise HTTPException(409, "This payment already completed. Its credits have been applied.")
    if transaction["status"] != "canceled":
        await paddle("PATCH", f"transactions/{transaction['id']}", {"status": "canceled"})
    await clear_pending(uid, pending["id"], f"checkout_cancel:{transaction['id']}")
    return {"cancelled": True}


@billing_router.post("/change-plan")
async def change_plan(body: CheckoutRequest, request: Request):
    user = await _get_session_user(request)
    await enforce_rate_limit(request, "change_plan", 10, 3600, identity=user["user_id"])
    item = CATALOG.get(body.item)
    if not item or item["mode"] != "subscription":
        raise HTTPException(400, "Choose a monthly plan")
    price = await validated_price(item)
    state = await wallet(user["user_id"])
    if not state.get("subscription"):
        raise HTTPException(409, "Subscribe before changing plans")
    sub = await paddle("GET", f"subscriptions/{state['subscription']}")
    if sub["customer_id"] != state.get("customer") or sub["status"] != "active" or sub.get("scheduled_change"):
        raise HTTPException(409, "Resolve your subscription status in the customer portal before changing plans.")
    sub = await paddle("PATCH", f"subscriptions/{sub['id']}", {
        "items": [{"price_id": price, "quantity": 1}], "proration_billing_mode": "do_not_bill"})
    await sync_subscription(sub)
    return {"message": "Plan updated. Your new price and credit allowance apply at your next paid renewal."}


@billing_router.post("/portal")
async def portal(request: Request):
    user = await _get_session_user(request)
    state = await wallet(user["user_id"])
    if not state.get("customer"):
        raise HTTPException(400, "No billing account yet")
    result = await paddle("POST", f"customers/{state['customer']}/portal-sessions", {})
    return {"url": result["urls"]["general"]["overview"]}


def verify_signature(raw, header):
    secret = os.environ.get("PADDLE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(503, "Webhook is not configured")
    try:
        parts = [part.strip().split("=", 1) for part in header.split(";")]
        stamp = next(v for k, v in parts if k == "ts")
        signatures = [v for k, v in parts if k == "h1"]
        expected = hmac.new(secret.encode(), stamp.encode() + b":" + raw, hashlib.sha256).hexdigest()
        if abs(time.time() - int(stamp)) > 300 or not any(hmac.compare_digest(expected, sig) for sig in signatures):
            raise ValueError()
        return json.loads(raw)
    except (ValueError, StopIteration, TypeError):
        raise HTTPException(400, "Invalid webhook signature")


def price_item(price_id):
    if not price_id:
        return None, None
    return next(((key, item) for key, item in [*CATALOG.items(), *LEGACY_CATALOG.items()]
                 if os.environ.get(item["env"]) == price_id), (None, None))


async def transaction_owner(transaction):
    uid = (transaction.get("custom_data") or {}).get("roundtable_user_id")
    if not uid:
        customer = await paddle("GET", f"customers/{transaction['customer_id']}")
        uid = (customer.get("custom_data") or {}).get("roundtable_user_id")
    if not uid:
        raise HTTPException(400, "Payment has no account reference")
    state = await wallet(uid)
    if state.get("customer") != transaction.get("customer_id"):
        raise HTTPException(400, "Payment customer mismatch")
    return uid


def transaction_item(transaction):
    items = transaction.get("items", [])
    if len(items) != 1 or items[0].get("quantity") != 1:
        raise HTTPException(400, "Payment does not match a credit product")
    key, item = price_item(items[0].get("price", {}).get("id"))
    if not item:
        raise HTTPException(400, "Unknown payment price")
    return key, item


async def fulfill_transaction(transaction):
    if transaction.get("status") != "completed":
        return
    if transaction.get("origin") in {"subscription_update", "subscription_payment_method_change", "subscription_charge"}:
        return
    uid = await transaction_owner(transaction)
    plan, item = transaction_item(transaction)
    sid = transaction.get("subscription_id")
    if item["mode"] == "payment":
        if sid:
            raise HTTPException(400, "A credit pack cannot be recurring")
        def grant(state):
            state["topup"] += item["credits"] * credits.SCALE
            return {"kind": "topup", "credits": item["credits"], "transaction_id": transaction["id"]}
        await credits.change(uid, f"paddle_transaction:{transaction['id']}", grant)
    else:
        if not sid:
            raise HTTPException(503, "Subscription creation is still processing")
        sub = await paddle("GET", f"subscriptions/{sid}")
        # Initial transactions may lack billing_period; renewal periods always
        # come from the paid transaction, never from today's subscription state.
        period = transaction.get("billing_period")
        if not period and transaction.get("origin") in {"api", "web"}:
            initial_period = sub.get("current_billing_period") or {}
            if sub.get("first_billed_at") and timestamp(sub["first_billed_at"]) == timestamp(initial_period.get("starts_at")):
                period = initial_period
        if not period:
            raise HTTPException(503, "Payment has no billing period")
        start, end = timestamp(period["starts_at"]), timestamp(period["ends_at"])
        def grant(state):
            credits.grant_monthly(state, item["credits"] * credits.SCALE, start, end, plan,
                                  sid, rollover=bool(item.get("rollover")))
            return {"kind": "monthly", "credits": item["credits"], "rollover_credits": state.get("rollover", 0) / credits.SCALE, "period_start": start,
                    "period_end": end, "transaction_id": transaction["id"]}
        await credits.change(uid, f"paddle_period:{sid}:{start}", grant)
        await sync_subscription(sub)
    order_id = (transaction.get("custom_data") or {}).get("order_id")
    if order_id:
        await clear_pending(uid, order_id, f"checkout_paid:{transaction['id']}")


async def sync_subscription(sub):
    uid = (sub.get("custom_data") or {}).get("roundtable_user_id")
    if not uid:
        customer = await paddle("GET", f"customers/{sub['customer_id']}")
        uid = (customer.get("custom_data") or {}).get("roundtable_user_id")
    if not uid:
        return
    state = await wallet(uid)
    if state.get("customer") != sub.get("customer_id"):
        raise HTTPException(400, "Subscription customer mismatch")
    plan, _ = price_item(sub["items"][0]["price"]["id"])
    created, updated = timestamp(sub["created_at"]), timestamp(sub["updated_at"])
    def sync(state):
        if created < state.get("subscription_created", 0):
            return {"kind": "subscription", "ignored": True}
        if state.get("subscription") == sub["id"] and updated < state.get("subscription_updated", 0):
            return {"kind": "subscription", "ignored": True}
        active = sub["status"] in {"active", "past_due"}
        state.update(subscription=sub["id"], subscription_created=created, subscription_updated=updated,
                     status=sub["status"], plan=(state.get("grant_plan") or plan or "free") if active else "free",
                     next_plan=plan if active else None,
                     period_end=timestamp((sub.get("current_billing_period") or {}).get("ends_at")))
        return {"kind": "subscription", "status": sub["status"]}
    # A subscription snapshot can be seen before its payment. Include the paid
    # grant revision so sync can reflect a newly granted plan on the same snapshot.
    revision = f"{sub['updated_at']}:{state.get('grant_start', 0)}:{state.get('grant_plan', '')}"
    await credits.change(uid, f"paddle_subscription:{sub['id']}:{revision}", sync)


async def reconcile_adjustment(adjustment, event):
    transaction = await paddle("GET", f"transactions/{adjustment['transaction_id']}")
    uid = await transaction_owner(transaction)
    _, item = transaction_item(transaction)
    adjustments = await paddle("GET", "adjustments", {"transaction_id": transaction["id"], "per_page": 200})
    financial = [a for a in adjustments if a["status"] == "approved" and a["action"] in {"refund", "credit", "chargeback"}]
    warning = any(a["status"] == "approved" and a["action"] == "chargeback_warning" for a in adjustments)
    revision = timestamp(event["occurred_at"])
    paid_total = int(transaction.get("details", {}).get("totals", {}).get("grand_total") or 0)
    uncertain = any(a.get("currency_code") != transaction.get("currency_code") for a in financial)
    refunded = sum(abs(int(a.get("totals", {}).get("total") or 0)) for a in financial)
    revoked = min(item["credits"] * credits.SCALE, round(item["credits"] * credits.SCALE * refunded / paid_total)) if paid_total else 0
    def reconcile(state):
        revisions = state.setdefault("adjustment_revisions", {})
        if revision < revisions.get(transaction["id"], 0):
            return {"kind": "adjustment", "ignored": True}
        revisions[transaction["id"]] = revision
        reviews = state.setdefault("payment_reviews", {})
        reviews[transaction["id"]] = warning or bool(financial and (item["mode"] == "subscription" or uncertain or not paid_total))
        state["payment_review"] = any(reviews.values())
        delta = 0
        if item["mode"] == "payment" and not uncertain and paid_total:
            reversals = state.setdefault("reversals", {})
            delta = revoked - reversals.get(transaction["id"], 0)
            if delta >= 0:
                taken = min(state["topup"], delta)
                state["topup"] -= taken
                state["debt"] += delta - taken
            else:
                recovered = min(state["debt"], -delta)
                state["debt"] -= recovered
                state["topup"] += -delta - recovered
            reversals[transaction["id"]] = revoked
        return {"kind": "refund" if delta > 0 else "adjustment", "credits": abs(delta) / credits.SCALE,
                "transaction_id": transaction["id"], "review_required": state["payment_review"]}
    await credits.change(uid, f"paddle_adjustment:{event['event_id']}", reconcile)


async def fulfill(event):
    obj, kind = event["data"], event["event_type"]
    if kind == "transaction.completed":
        await fulfill_transaction(await paddle("GET", f"transactions/{obj['id']}"))
    elif kind.startswith("subscription."):
        await sync_subscription(await paddle("GET", f"subscriptions/{obj['id']}"))
    elif kind in {"adjustment.created", "adjustment.updated"}:
        adjustment = await paddle("GET", f"adjustments/{obj['id']}")
        await reconcile_adjustment(adjustment, event)


@billing_router.post("/webhook")
async def webhook(request: Request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 1024 * 1024:
            raise HTTPException(413, "Webhook too large")
    event = verify_signature(bytes(raw), request.headers.get("paddle-signature", ""))
    await fulfill(event)
    return {"received": True}
