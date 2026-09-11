"""Versioned sale prices; legacy IDs remain valid for renewals and refunds."""
CATALOG = {
    "pro": {"name": "Writer", "credits": 200, "cents": 1500, "mode": "subscription", "env": "PADDLE_PRICE_WRITER_V2", "rollover": True},
    "studio": {"name": "Studio", "credits": 450, "cents": 2900, "mode": "subscription", "env": "PADDLE_PRICE_STUDIO_V2", "rollover": True},
    "topup_100": {"name": "Small reading pack", "credits": 100, "cents": 1000, "mode": "payment", "env": "PADDLE_PRICE_PACK_100"},
    "topup_220": {"name": "Medium reading pack", "credits": 220, "cents": 2000, "mode": "payment", "env": "PADDLE_PRICE_PACK_220"},
    "topup_400": {"name": "Large reading pack", "credits": 400, "cents": 3500, "mode": "payment", "env": "PADDLE_PRICE_PACK_400"},
}

# Never reinterpret an existing paid price as the new, cheaper offer.
LEGACY_CATALOG = {
    "pro": {"name": "Pro (legacy)", "credits": 200, "cents": 1900, "mode": "subscription", "env": "PADDLE_PRICE_PRO"},
    "studio": {"name": "Studio (legacy)", "credits": 600, "cents": 4900, "mode": "subscription", "env": "PADDLE_PRICE_STUDIO"},
    "topup_100": {"name": "100 credits (legacy)", "credits": 100, "cents": 1200, "mode": "payment", "env": "PADDLE_PRICE_TOPUP_100"},
    "topup_250": {"name": "250 credits (legacy)", "credits": 250, "cents": 3000, "mode": "payment", "env": "PADDLE_PRICE_TOPUP_250"},
}
