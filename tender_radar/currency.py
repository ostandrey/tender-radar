"""Currency conversion to UAH using the official National Bank of Ukraine (NBU) rates."""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

NBU_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"

# Used only when the NBU is unreachable. Rough values; meta.json flags them as "fallback".
FALLBACK_RATES = {"UAH": 1.0, "USD": 41.5, "EUR": 48.0, "GBP": 56.0, "PLN": 11.2}


def parse_nbu_rates(payload: list[dict[str, Any]]) -> tuple[dict[str, float], str]:
    """Turn the NBU JSON into ``({"USD": 41.2, ...}, "2026-11-17")``.

    Each row looks like ``{"cc": "USD", "rate": 41.2, "exchangedate": "17.11.2026"}``.
    """
    rates = {row["cc"]: float(row["rate"]) for row in payload}
    rates["UAH"] = 1.0
    raw_date = payload[0].get("exchangedate", "") if payload else ""
    day, month, year = (raw_date.split(".") + ["", "", ""])[:3]
    iso = f"{year}-{month}-{day}" if year else ""
    return rates, iso


class RateProvider:
    """Holds UAH-per-unit rates and converts amounts."""

    def __init__(self, rates: dict[str, float] | None = None, source: str = "") -> None:
        self.rates: dict[str, float] = {"UAH": 1.0, **(rates or {})}
        self.rates_date = ""
        self.source = source or ("given" if rates else "")

    async def load(self, client: httpx.AsyncClient) -> None:
        """Fetch today's NBU rates; fall back to rough constants on failure."""
        try:
            resp = await client.get(NBU_URL)
            resp.raise_for_status()
            self.rates, self.rates_date = parse_nbu_rates(resp.json())
            self.source = "NBU"
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning("NBU rates unavailable (%s); using fallback rates", exc)
            self.rates, self.rates_date, self.source = dict(FALLBACK_RATES), "", "fallback"

    def to_uah(self, amount: float | None, currency: str) -> float | None:
        """Convert ``amount`` to UAH, or ``None`` if the amount or the rate is unknown."""
        rate = self.rates.get((currency or "").upper())
        if amount is None or rate is None:
            return None
        return round(amount * rate, 2)
