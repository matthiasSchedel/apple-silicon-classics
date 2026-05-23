#!/usr/bin/env python3
"""Poll store APIs for classic-game deal triggers."""

from __future__ import annotations

import html
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
WATCHLIST_PATH = ROOT / "data" / "watchlist.json"
HISTORY_PATH = ROOT / "data" / "price-history.json"
FANATICAL_ALL_URL = "https://www.fanatical.com/api/all/en"
GOG_CATALOG_URL = "https://catalog.gog.com/v1/catalog"
STEAM_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

BOT = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT = os.environ.get("TELEGRAM_CHAT_ID")


@dataclass(frozen=True)
class StorePrice:
    store: str
    final_usd: float
    base_usd: float
    discount_percent: int
    url: str

    @property
    def final_label(self) -> str:
        return f"${self.final_usd:.2f}"

    @property
    def base_label(self) -> str:
        return f"${self.base_usd:.2f}"

    @property
    def discount_label(self) -> str:
        return f"-{self.discount_percent}%" if self.discount_percent else "0%"


@dataclass(frozen=True)
class Alert:
    title: str
    store: str
    final: str
    base: str
    discount: str
    url: str
    reason: str


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def parse_usd(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def normalize(text: str) -> str:
    text = text.casefold().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def request_json(session: requests.Session, url: str, **kwargs: Any) -> Any:
    response = session.get(url, timeout=20, **kwargs)
    response.raise_for_status()
    return response.json()


def gog_price(session: requests.Session, game: dict[str, Any]) -> StorePrice | None:
    slug = game.get("gog_slug")
    if not slug:
        return None
    query = game.get("gog_query") or game["title"]
    data = request_json(
        session,
        GOG_CATALOG_URL,
        params={
            "query": query,
            "limit": 10,
            "currencyCode": "USD",
            "countryCode": "US",
            "locale": "en-US",
        },
    )
    for product in data.get("products", []):
        if product.get("slug") != slug:
            continue
        price = product.get("price") or {}
        final_usd = parse_usd((price.get("finalMoney") or {}).get("amount")) or parse_usd(price.get("final"))
        base_usd = parse_usd((price.get("baseMoney") or {}).get("amount")) or parse_usd(price.get("base"))
        if final_usd is None or base_usd is None:
            return None
        discount = int(round(max(0.0, (1 - final_usd / base_usd) * 100))) if base_usd else 0
        return StorePrice(
            store="GOG",
            final_usd=final_usd,
            base_usd=base_usd,
            discount_percent=discount,
            url=f"https://www.gog.com/en/game/{slug}",
        )
    print(f"GOG product not found for {game['slug']} ({slug})", file=sys.stderr)
    return None


def steam_price(session: requests.Session, game: dict[str, Any]) -> StorePrice | None:
    appid = game.get("steam_appid")
    if not appid:
        return None
    data = request_json(
        session,
        STEAM_DETAILS_URL,
        params={"appids": appid, "cc": "us", "filters": "price_overview"},
    )
    payload = data.get(str(appid), {}).get("data", {})
    if not isinstance(payload, dict):
        print(f"Steam price unavailable for {game['slug']} ({appid})", file=sys.stderr)
        return None
    price = payload.get("price_overview")
    if not price:
        print(f"Steam price unavailable for {game['slug']} ({appid})", file=sys.stderr)
        return None
    final_usd = parse_usd(price.get("final") / 100)
    base_usd = parse_usd(price.get("initial") / 100)
    if final_usd is None or base_usd is None:
        return None
    return StorePrice(
        store="Steam",
        final_usd=final_usd,
        base_usd=base_usd,
        discount_percent=int(price.get("discount_percent") or 0),
        url=f"https://store.steampowered.com/app/{appid}/",
    )


def fanatical_bundles(session: requests.Session) -> list[dict[str, Any]]:
    try:
        data = request_json(session, FANATICAL_ALL_URL)
    except requests.RequestException as exc:
        print(f"Fanatical lookup failed: {exc}", file=sys.stderr)
        return []
    return [*data.get("pickandmix", []), *data.get("mystery", [])]


def game_terms(game: dict[str, Any]) -> set[str]:
    terms = {normalize(game["title"])}
    for term in game.get("fanatical_terms") or []:
        normalized = normalize(term)
        if len(normalized) >= 3:
            terms.add(normalized)
    return terms


def product_matches(game: dict[str, Any], product: dict[str, Any]) -> bool:
    name = normalize(product.get("name", ""))
    slug = normalize(product.get("slug", ""))
    haystack = {name, slug}
    for term in game_terms(game):
        if len(term) <= 2:
            continue
        if term in haystack:
            return True
    return False


def fanatical_alerts(
    games: list[dict[str, Any]],
    bundles: list[dict[str, Any]],
    history: dict[str, Any],
) -> list[Alert]:
    alerts: list[Alert] = []
    seen = set(history.setdefault("fanatical_seen", []))
    for bundle in bundles:
        products = bundle.get("products") or []
        if not products:
            continue
        bundle_slug = bundle.get("slug") or bundle.get("sku") or bundle.get("_id")
        bundle_name = bundle.get("name") or "Fanatical bundle"
        bundle_url = f"https://www.fanatical.com/en/pick-and-mix/{bundle_slug}"
        if bundle.get("type") not in {None, "game-bundle"}:
            bundle_url = f"https://www.fanatical.com/en/bundle/{bundle_slug}"
        for game in games:
            if not any(product_matches(game, product) for product in products):
                continue
            key = f"{game['slug']}:{bundle_slug}"
            if key in seen:
                continue
            seen.add(key)
            alerts.append(
                Alert(
                    title=game["title"],
                    store="Fanatical",
                    final="bundle",
                    base="bundle",
                    discount="bundle",
                    url=bundle_url,
                    reason=f"new bundle match: {bundle_name}",
                )
            )
    history["fanatical_seen"] = sorted(seen)
    return alerts


def should_alert_price(history: dict[str, Any], price: StorePrice, game: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    threshold = game.get("watch_below_usd")
    discount_threshold = game.get("watch_discount_percent")
    previous_checks = history.get("checks") or []
    previous_usd = previous_checks[-1]["usd"] if previous_checks else None
    current_low = history.get("low_usd")

    if threshold is not None and price.final_usd <= float(threshold):
        prior_threshold_usd = history.get("last_threshold_alert_usd")
        crossed_down = previous_usd is not None and previous_usd > float(threshold)
        improved_threshold = prior_threshold_usd is None or price.final_usd < float(prior_threshold_usd)
        if crossed_down or improved_threshold:
            history["last_threshold_alert_usd"] = price.final_usd
            reasons.append(f"hit watch threshold ${float(threshold):.2f}")

    if discount_threshold is not None and price.discount_percent >= int(discount_threshold):
        prior_discount = history.get("last_discount_alert_percent")
        improved_discount = prior_discount is None or price.discount_percent > int(prior_discount)
        crossed_discount = previous_checks and int(previous_checks[-1].get("discount_percent", 0)) < int(discount_threshold)
        if improved_discount or crossed_discount:
            history["last_discount_alert_percent"] = price.discount_percent
            reasons.append(f"{price.discount_label} meets {int(discount_threshold)}% watch drop")

    if current_low is not None and price.final_usd < float(current_low):
        reasons.append("NEW HISTORICAL LOW")
    history["low_usd"] = min(float(current_low), price.final_usd) if current_low is not None else price.final_usd
    return reasons


def append_check(history: dict[str, Any], price: StorePrice) -> None:
    checks = history.setdefault("checks", [])
    checks.append(
        {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "store": price.store,
            "usd": price.final_usd,
            "base_usd": price.base_usd,
            "discount_percent": price.discount_percent,
        }
    )
    history["checks"] = checks[-50:]


def notify(text: str) -> None:
    if not BOT or not CHAT:
        print("Telegram not configured; alert preview:")
        print(text)
        return
    response = requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        json={
            "chat_id": CHAT,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    response.raise_for_status()


def render_alerts(alerts: list[Alert]) -> str:
    lines = ["<b>Classic-games deal alert</b>", ""]
    for alert in alerts[:20]:
        title = html.escape(alert.title)
        reason = html.escape(alert.reason)
        store = html.escape(alert.store)
        final = html.escape(alert.final)
        base = html.escape(alert.base)
        discount = html.escape(alert.discount)
        url = html.escape(alert.url, quote=True)
        lines.append(
            f'- <a href="{url}">{title}</a> - {final} '
            f"(was {base}, {discount}) @ {store} - <i>{reason}</i>"
        )
    if len(alerts) > 20:
        lines.append(f"\n{len(alerts) - 20} more alert(s) omitted from Telegram message.")
    return "\n".join(lines)


def main() -> int:
    watchlist = load_json(WATCHLIST_PATH, {"games": []})
    history = load_json(HISTORY_PATH, {})
    games = watchlist["games"]
    session = requests.Session()
    session.headers.update({"User-Agent": "apple-silicon-classics-deals/1.0"})

    alerts: list[Alert] = []
    for game in games:
        game_history = history.setdefault(game["slug"], {"low_usd": None, "checks": []})
        prices = [price for price in (gog_price(session, game), steam_price(session, game)) if price]
        if not prices:
            continue
        cheapest = min(prices, key=lambda price: price.final_usd)
        reasons = should_alert_price(game_history, cheapest, game)
        append_check(game_history, cheapest)
        if reasons:
            alerts.append(
                Alert(
                    title=game["title"],
                    store=cheapest.store,
                    final=cheapest.final_label,
                    base=cheapest.base_label,
                    discount=cheapest.discount_label,
                    url=cheapest.url,
                    reason="; ".join(dict.fromkeys(reasons)),
                )
            )

    alerts.extend(fanatical_alerts(games, fanatical_bundles(session), history))
    HISTORY_PATH.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n")

    if alerts:
        notify(render_alerts(alerts))
    else:
        print("No triggers; price history updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
