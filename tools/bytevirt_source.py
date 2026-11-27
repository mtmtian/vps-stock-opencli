"""Collect eligible ByteVirt Japan ISP and Los Angeles CN2 GIA offers."""

from __future__ import annotations

from importlib import import_module
import json
from pathlib import Path
import sys
from typing import Any


CATALOG_URL = "https://bytevirt.com/index.php?m=bvstore&action=catalog"
STORE_URL = "https://bytevirt.com/index.php?m=bvstore"
PRICE_CEILING_USD = 15.0
LA_ANNUAL_PID = 329
LA_ANNUAL_CEILING_USD = 66
JP_PREPAID_PID = 324
JP_PREPAID_KEY = f"{JP_PREPAID_PID}-prepaid"
JP_TERM_LIMITS = {"quarter": 25, "half-year": 40, "year": 69}
CYCLE_PERIODS = {"monthly": "month", "quarterly": "quarter", "semiannually": "half-year", "annually": "year"}
REQUEST_TIMEOUT_SECONDS = 20
FIXED_PRODUCT_IDS = frozenset({325, 330})


def _load_stock_parser() -> Any:
    parser_path = Path(__file__).resolve().with_name("vps_stock.py")
    main = sys.modules.get("__main__")
    if main and getattr(main, "__file__", None) and Path(main.__file__).resolve() == parser_path:
        return main
    return import_module(".vps_stock", __package__) if __package__ else import_module("vps_stock")


def _bytevirt_targets(parser: Any) -> list[dict[str, Any]]:
    configured = {
        provider["product_id"]: provider
        for provider in parser.PROVIDERS
        if provider.get("kind") == "bytevirt_json"
        and provider.get("product_id") in FIXED_PRODUCT_IDS
    }
    if set(configured) != FIXED_PRODUCT_IDS:
        raise RuntimeError("The local VPS stock parser must define ByteVirt PIDs 325 and 330")
    targets = [configured[product_id] for product_id in sorted(FIXED_PRODUCT_IDS)]
    return targets


def _target_family(
    product: dict[str, Any], targets: list[dict[str, Any]]
) -> dict[str, Any] | None:
    for target in targets:
        if target["target_region"] == "JP":
            if product.get("region") == "JP" and product.get("tier") == "isp":
                return target
        elif (
            product.get("region_label") == "US (LA)"
            and product.get("subtier") == "cn2gia"
        ):
            return target
    return None


def _provider_for_product(
    product: dict[str, Any], target: dict[str, Any], expected_target: bool
) -> dict[str, Any]:
    if expected_target:
        return dict(target)

    product_id = product["pid"]
    return {
        "id": "bytevirt-%s" % product_id,
        "provider": target["provider"],
        "region": product.get("region_label", target["region"]),
        "kind": target["kind"],
        "url": target["url"],
        "product_id": product_id,
        "plan_name": product["name"],
        "target_region": product.get("region"),
        "target_line": product.get("line"),
        "target_tier": product.get("tier"),
        "target_subtier": product.get("subtier", ""),
        "monthly_price_ceiling": PRICE_CEILING_USD,
        "priority": target["priority"],
        "network": target["network"],
    }


def _empty_record(product: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    name = product.get("name")
    if not isinstance(name, str):
        name = target["plan_name"]
    region = product.get("region_label")
    if not isinstance(region, str):
        region = product.get("region", target["region"])
    return {
        "name": name,
        "available": None,
        "price": None,
        "quantity": None,
        "region": region,
        "url": STORE_URL,
    }


def _record_for_product(
    product: dict[str, Any],
    target: dict[str, Any],
    expected_target: bool,
    parser: Any,
    text: str,
) -> dict[str, Any]:
    provider = _provider_for_product(product, target, expected_target)
    checked = parser.check_bytevirt_json(provider, 200, text)
    record = _empty_record(product, target)

    plans = checked.get("plans", [])
    status = checked.get("status")
    if status not in {"available", "out_of_stock", "offer_changed"} or len(plans) != 1:
        return record

    plan = plans[0]
    price = plan.get("price")
    record["quantity"] = plan.get("count")
    if status == "offer_changed":
        record["available"] = False
        if isinstance(price, dict) and price.get("currency") == "USD":
            record["price"] = price.get("amount")
        return record

    if not isinstance(price, dict) or not price.get("price_eligible"):
        return record
    record["available"] = plan["available"]
    record["price"] = price["amount"]
    return record


def collect(timeout: float = REQUEST_TIMEOUT_SECONDS) -> dict[str, dict[str, Any]]:
    """Fetch and validate current eligible ByteVirt products in one request.

    The result includes products in the two configured families whose monthly
    USD price is at most $15 and whose catalog entry claims one dedicated IPv4.
    The original two monitored PIDs remain present with ``None`` fields if an
    item-level stock, price, or schema check fails. Callers can then preserve
    that item's last valid state while continuing to update other products.
    """
    parser = _load_stock_parser()
    targets = _bytevirt_targets(parser)
    status_code, text = parser.fetch(
        CATALOG_URL, timeout=timeout
    )
    if status_code != 200:
        raise RuntimeError("ByteVirt catalog returned HTTP %s" % status_code)

    try:
        catalog = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("ByteVirt catalog response is not valid JSON") from exc
    products = catalog.get("public_vps") if isinstance(catalog, dict) else None
    if not isinstance(products, list):
        raise RuntimeError("ByteVirt catalog response has no public VPS list")

    expected_by_id: dict[int, dict[str, Any]] = {}
    matching: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for target in targets:
        expected_by_id[target["product_id"]] = target

    for product in products:
        if not isinstance(product, dict):
            continue
        product_id = product.get("pid")
        if not isinstance(product_id, int) or isinstance(product_id, bool):
            continue
        target = _target_family(product, targets)
        if target is not None:
            matching.append((product, target))

    matching_pids = {product["pid"] for product, _ in matching}
    missing = set(expected_by_id) - matching_pids
    if missing:
        raise RuntimeError(
            "ByteVirt catalog is missing expected target PIDs %s"
            % ", ".join(str(product_id) for product_id in sorted(missing))
        )

    results: dict[str, dict[str, Any]] = {}
    for product, target in matching:
        product_id = product["pid"]
        is_expected = product_id in expected_by_id
        spec = product.get("spec")
        if not isinstance(spec, dict) or "ipv4" not in spec:
            results[str(product_id)] = _empty_record(product, target)
            continue
        if spec.get("ipv4") != "1":
            if is_expected:
                results[str(product_id)] = _empty_record(product, target)
            continue

        if not isinstance(product.get("name"), str):
            results[str(product_id)] = _empty_record(product, target)
            continue

        results[str(product_id)] = _record_for_product(
            product, target, is_expected, parser, text
        )

    for product_id, target in expected_by_id.items():
        results.setdefault(
            str(product_id),
            {
                "name": target["plan_name"],
                "available": None,
                "price": None,
                "quantity": None,
                "region": target["region"],
                "url": STORE_URL,
            },
        )

    annual_target = dict(expected_by_id[330], product_id=LA_ANNUAL_PID,
                         plan_name="VPS-512-KVM-CN2 GIA LA", billing_cycle="annually",
                         annual_price_ceiling=LA_ANNUAL_CEILING_USD)
    annual_product = next((p for p, _ in matching if p["pid"] == LA_ANNUAL_PID), None)
    if annual_product is None:
        annual_record = _empty_record({}, annual_target)
    else:
        annual_record = _record_for_product(annual_product, annual_target, True, parser, text)
    results[f"{LA_ANNUAL_PID}-year"] = dict(annual_record, period="year")
    # All three terms draw on the same stock. Keep one transition per restock.
    jp_target = dict(expected_by_id[325], product_id=JP_PREPAID_PID, plan_name="VPS-512-KVM-ISP-JP")
    jp_product = next((p for p, _ in matching if p["pid"] == JP_PREPAID_PID), None)
    selected = _empty_record({}, jp_target)
    if jp_product is not None:
        uncertain = False
        for cycle, period in CYCLE_PERIODS.items():
            if period not in JP_TERM_LIMITS:
                continue
            limit = JP_TERM_LIMITS[period]
            target = dict(jp_target, billing_cycle=cycle, term_price_ceiling=limit)
            row = _record_for_product(jp_product, target, True, parser, text)
            if row["available"] is None:
                uncertain = True
            elif row["price"] is not None and row["price"] <= limit:
                selected = dict(row, period=period)
                break
        else:
            selected["available"] = None if uncertain else False
    results[JP_PREPAID_KEY] = selected
    return results
