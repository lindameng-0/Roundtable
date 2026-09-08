"""Atomic, auditable credit accounting shared by API and worker processes."""
import asyncio
import copy
import math
import time
import uuid

import config as cfg

SCALE = 1000
BUCKETS = ("rollover", "monthly", "starter", "topup")


class InsufficientCredits(RuntimeError):
    def __init__(self, available=0, required=0):
        self.details = {"code": "insufficient_credits", "available_credits": available / SCALE,
                        "required_credits": required / SCALE,
                        "message": "Not enough credits. Add credits on the billing page to continue."}
        super().__init__(self.details["message"])


def units(cost):
    if cost is None or not math.isfinite(float(cost)) or cost < 0:
        raise ValueError("Cannot meter an unknown or invalid model price")
    return max(1, math.ceil(float(cost) * cfg.CREDITS_PER_USD * SCALE))


def normalize(data):
    state = copy.deepcopy(data or {})
    for bucket in BUCKETS:
        state.setdefault(bucket, 0)
    state.setdefault("holds", {})
    state.setdefault("plan", "free")
    state.setdefault("debt", 0)
    if state.get("grant_end", 0) <= time.time():
        if state["monthly"] and state.get("grant_rollover"):
            state["expired_monthly"] = {"amount": state["monthly"], "end": state["grant_end"]}
        state["monthly"] = 0
    if state.get("rollover_end", 0) <= time.time():
        state["rollover"] = 0
    # Reversed payments are recovered from unspent credits and future grants.
    for bucket in ("topup", "rollover", "monthly", "starter"):
        recovered = min(state[bucket], state["debt"])
        state[bucket] -= recovered
        state["debt"] -= recovered
    return state


def grant_monthly(state, amount, start, end, plan, subscription_id, *, rollover=False):
    """Grant a paid period once. Only its predecessor's unused monthly grant rolls."""
    if start <= state.get("grant_start", -1):
        return
    previous_end = state.get("grant_end", 0)
    continuous = previous_end == start and state.get("grant_subscription") == subscription_id
    unspent = state.get("monthly", 0)
    expired = state.get("expired_monthly") or {}
    if expired.get("end") == previous_end:
        unspent = expired.get("amount", 0)
    carry = min(unspent, amount) if continuous and rollover and state.get("grant_rollover") else 0
    live = end > time.time()
    state.update(monthly=amount if live else 0, rollover=carry if live else 0,
                 rollover_end=end, grant_start=start, grant_end=end, grant_plan=plan,
                 grant_subscription=subscription_id, grant_rollover=rollover)
    state.pop("expired_monthly", None)


async def change(user_id, key, mutate):
    """Optimistic concurrency with an atomic SQL commit and permanent receipt."""
    receipt_id = f"{user_id}:{key}"
    for attempt in range(30):
        receipt = await cfg.db.credit_entries.find_one({"id": receipt_id})
        if receipt:
            return receipt["data"]
        row = await cfg.db.credit_wallets.find_one({"id": user_id}) or {"version": 0, "data": {}}
        state = normalize(row["data"])
        result = mutate(state)
        if await cfg.db.apply_credit_change(user_id, row["version"], state, receipt_id, result):
            return result
        await asyncio.sleep(min(0.005 * (attempt + 1), 0.1))
    raise RuntimeError("Credit balance is busy. Please retry.")


async def ensure_wallet(user_id):
    def starter(state):
        state["starter"] += cfg.STARTER_CREDITS * SCALE
        state["starter_granted"] = cfg.STARTER_CREDITS
        return {"kind": "starter", "credits": cfg.STARTER_CREDITS}
    original = await change(user_id, "starter", starter)
    # Existing accounts receive only the difference, once; spent credits stay spent.
    if original.get("credits", 0) < cfg.STARTER_CREDITS:
        def upgrade(state):
            granted = state.get("starter_granted", original.get("credits", 0))
            extra = max(0, cfg.STARTER_CREDITS - granted)
            state["starter"] += extra * SCALE
            state["starter_granted"] = max(granted, cfg.STARTER_CREDITS)
            return {"kind": "starter", "credits": extra}
        await change(user_id, f"starter_allowance:{cfg.STARTER_CREDITS}", upgrade)


async def balance(user_id):
    await ensure_wallet(user_id)
    row = await cfg.db.credit_wallets.find_one({"id": user_id})
    state = normalize(row["data"])
    # Model calls are bounded. Abandoned reservations are recoverable without
    # ever refunding a completed operation; settlement and release share a key.
    for rid, hold in list(state["holds"].items()):
        if hold["created"] < time.time() - 86400:
            await finish(user_id, rid, 0)
    if state["holds"]:
        row = await cfg.db.credit_wallets.find_one({"id": user_id})
        state = normalize(row["data"])
    return {"available_credits": max(0, sum(state[b] for b in BUCKETS) - state["debt"]) / SCALE,
            "rollover_credits": state["rollover"] / SCALE, "rollover_end": state.get("rollover_end"),
            "starter_credits": state["starter"] / SCALE, "monthly_credits": state["monthly"] / SCALE,
            "topup_credits": state["topup"] / SCALE,
            "reserved_credits": sum(h["amount"] for h in state["holds"].values()) / SCALE,
            "plan": state["plan"], "subscription_status": state.get("status", "none"),
            "payment_review": state.get("payment_review", False),
            "period_end": state.get("period_end"), "has_customer": bool(state.get("customer"))}


async def reserve(user_id, amount, label):
    await ensure_wallet(user_id)
    rid = str(uuid.uuid4())
    def take(state):
        available = sum(state[b] for b in BUCKETS)
        if state.get("payment_review") or state["debt"] or available < amount:
            raise InsufficientCredits(available, amount)
        left, split = amount, {}
        for bucket in BUCKETS:
            split[bucket] = min(state[bucket], left)
            state[bucket] -= split[bucket]
            left -= split[bucket]
        state["holds"][rid] = {"amount": amount, "split": split, "created": time.time(),
                               "period_end": state.get("grant_end", 0), "rollover_end": state.get("rollover_end", 0)}
        return {"kind": "reservation", "credits": amount / SCALE, "label": label}
    await change(user_id, f"reserve:{rid}", take)
    return f"credit:{user_id}:{rid}"


async def finish(user_id, rid, actual):
    def settle(state):
        hold = state["holds"].pop(rid, None)
        if not hold:
            raise RuntimeError("Unknown credit reservation")
        # A customer never pays more than was reserved for this call.
        charge = min(max(0, actual), hold["amount"])
        left = charge
        for bucket in BUCKETS:
            used = min(left, hold["split"].get(bucket, 0))
            left -= used
            refund = hold["split"].get(bucket, 0) - used
            expiry = "period_end" if bucket == "monthly" else "rollover_end"
            current_expiry = state.get("grant_end" if bucket == "monthly" else "rollover_end")
            if bucket not in {"monthly", "rollover"} or (hold.get(expiry) == current_expiry and (hold.get(expiry) or 0) > time.time()):
                state[bucket] += refund
        return {"kind": "usage" if charge else "release", "credits": charge / SCALE}
    return await change(user_id, f"finish:{rid}", settle)


async def settle_token(token, cost):
    _, user_id, rid = token.split(":", 2)
    return await finish(user_id, rid, units(cost) if cost else 0)
