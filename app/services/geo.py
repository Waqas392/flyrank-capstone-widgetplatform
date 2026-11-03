"""IP -> geolocation with a provider fallback chain: A, then B, then give up (never raise)."""
from __future__ import annotations

import asyncio
import ipaddress
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from .faults import Faults

log = logging.getLogger("geo")


@dataclass
class GeoResult:
    country: str | None
    city: str | None
    provider: str


class ProviderError(Exception):
    pass


class GeoProvider(Protocol):
    name: str

    async def lookup(self, ip: str) -> GeoResult: ...


class IpApiProvider:
    """Provider A - ip-api.com (free, no key, 45 req/min, HTTP only on the free tier)."""

    name = "ip-api"

    async def lookup(self, ip: str) -> GeoResult:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"http://ip-api.com/json/{ip}", params={"fields": "status,country,city"})
        r.raise_for_status()
        d = r.json()
        if d.get("status") != "success":
            raise ProviderError(f"ip-api status={d.get('status')}")
        return GeoResult(d.get("country"), d.get("city"), self.name)


class IpapiCoProvider:
    """Provider B - ipapi.co (free tier ~1,000/day, no key)."""

    name = "ipapi.co"

    async def lookup(self, ip: str) -> GeoResult:
        async with httpx.AsyncClient() as c:
            r = await c.get(f"https://ipapi.co/{ip}/json/")
        r.raise_for_status()
        d = r.json()
        if d.get("error"):
            raise ProviderError(f"ipapi.co error={d.get('reason')}")
        return GeoResult(d.get("country_name"), d.get("city"), self.name)


class MockProvider:
    """Deterministic stand-in: answers unless toggled down through Faults."""

    def __init__(self, key: str, faults: Faults, country: str, city: str):
        self.key, self.faults, self.country, self.city = key, faults, country, city
        self.name = f"mock-{key}"

    async def lookup(self, ip: str) -> GeoResult:
        if self.key in self.faults.geo_down:
            raise ProviderError(f"{self.name} is down (fault injected)")
        return GeoResult(self.country, self.city, self.name)


class GeoChain:
    def __init__(self, providers: list[GeoProvider], timeout: float, skip_private: bool):
        self.providers, self.timeout, self.skip_private = providers, timeout, skip_private

    async def enrich(self, ip: str) -> GeoResult | None:
        if self.skip_private:
            try:
                if not ipaddress.ip_address(ip).is_global:
                    return None
            except ValueError:
                return None
        for p in self.providers:
            try:
                return await asyncio.wait_for(p.lookup(ip), timeout=self.timeout)
            except Exception as exc:  # any failure -> try next provider
                log.warning("geo provider %s failed: %s", p.name, exc)
        log.warning("all geo providers failed; storing submission without geo")
        return None


def build_chain(mode: str, faults: Faults, timeout: float) -> GeoChain:
    if mode == "live":
        return GeoChain([IpApiProvider(), IpapiCoProvider()], timeout, skip_private=True)
    return GeoChain(
        [
            MockProvider("a", faults, "Mockland", "Alpha City"),
            MockProvider("b", faults, "Mockland", "Beta City"),
        ],
        timeout,
        skip_private=False,
    )
