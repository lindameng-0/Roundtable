"""Atomic, auditable credit accounting shared by API and worker processes."""
import asyncio
import copy
import math
import time
import uuid

import config as cfg

SCALE = 1000


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
    for bucket in ("starter", "monthly", "topup"):
        state.setdefault(bucket, 0)
    state.setdefault("holds", {})
    state.setdefault("plan", "free")
    state.setdefault("debt", 0)
    if state.get("grant_end", 0) <= time.time():
        state["monthly"] = 0
    # Reversed payments are recovered from unspent credits and future grants.
    for bucket in ("topup", "monthly", "starter"):
        recovered = min(state[bucket], state["debt"])
        state[bucket] -= recovered
        state["debt"] -= recovered
    return state


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
        return {"kind": "starter", "credits": cfg.STARTER_CREDITS}
    await change(user_id, "starter", starter)


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
    return {"available_credits": max(0, sum(state[b] for b in ("starter", "monthly", "topup")) - state["debt"]) / SCALE,
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
        available = sum(state[b] for b in ("monthly", "starter", "topup"))
        if state.get("payment_review") or state["debt"] or available < amount:
            raise InsufficientCredits(available, amount)
        left, split = amount, {}
        for bucket in ("monthly", "starter", "topup"):
            split[bucket] = min(state[bucket], left)
            state[bucket] -= split[bucket]
            left -= split[bucket]
        state["holds"][rid] = {"amount": amount, "split": split, "created": time.time(),
                               "period_end": state.get("grant_end", 0)}
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
        for bucket in ("monthly", "starter", "topup"):
            used = min(left, hold["split"][bucket])
            left -= used
            refund = hold["split"][bucket] - used
            if bucket != "monthly" or (hold["period_end"] == state.get("grant_end") and hold["period_end"] > time.time()):
                state[bucket] += refund
        return {"kind": "usage" if charge else "release", "credits": charge / SCALE}
    return await change(user_id, f"finish:{rid}", settle)


async def settle_token(token, cost):
    _, user_id, rid = token.split(":", 2)
    return await finish(user_id, rid, units(cost) if cost else 0)
