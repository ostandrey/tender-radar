import asyncio

import httpx

from tender_radar.currency import FALLBACK_RATES, RateProvider, parse_nbu_rates

NBU_PAYLOAD = [
    {"cc": "USD", "rate": 41.25, "exchangedate": "17.11.2026"},
    {"cc": "EUR", "rate": 48.5, "exchangedate": "17.11.2026"},
]


def test_parse_nbu_rates():
    rates, day = parse_nbu_rates(NBU_PAYLOAD)
    assert rates == {"USD": 41.25, "EUR": 48.5, "UAH": 1.0}
    assert day == "2026-11-17"


def test_conversion_with_fake_rates():
    provider = RateProvider({"EUR": 40.0})
    assert provider.to_uah(1000, "EUR") == 40000.0
    assert provider.to_uah(1000, "eur") == 40000.0  # case-insensitive
    assert provider.to_uah(55.5, "UAH") == 55.5


def test_unknown_currency_or_amount_gives_none():
    provider = RateProvider({"EUR": 40.0})
    assert provider.to_uah(10, "XYZ") is None
    assert provider.to_uah(None, "EUR") is None


def _load(handler) -> RateProvider:
    async def run() -> RateProvider:
        provider = RateProvider()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await provider.load(client)
        return provider

    return asyncio.run(run())


def test_load_from_nbu():
    provider = _load(lambda request: httpx.Response(200, json=NBU_PAYLOAD))
    assert provider.source == "NBU"
    assert provider.to_uah(2, "USD") == 82.5


def test_load_falls_back_when_nbu_is_down():
    provider = _load(lambda request: httpx.Response(503))
    assert provider.source == "fallback"
    assert provider.rates["USD"] == FALLBACK_RATES["USD"]
