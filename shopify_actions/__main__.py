"""python -m shopify_actions <product_url> [options]"""

from __future__ import annotations

import argparse
import json
import sys

from .checkout import (
    BuyerInfo,
    load_buyer_from_file,
    open_checkout,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m shopify_actions",
        description=(
            "Resolve a Shopify product URL, build a qty-1 cart permalink with "
            "optional buyer prefills, and open checkout in the default browser. "
            "Payment / MFA stay manual."
        ),
    )
    p.add_argument(
        "product_url",
        help="Full product URL, /products/{handle} path, or bare handle "
        "(bare handle needs --shop-origin / SHOPIFY_SHOP_ORIGIN)",
    )
    p.add_argument(
        "-q",
        "--quantity",
        type=int,
        default=1,
        help="Quantity to add (default: 1)",
    )
    p.add_argument(
        "--variant-id",
        type=int,
        default=None,
        help="Force a specific variant id instead of auto-pick",
    )
    p.add_argument(
        "--shop-origin",
        default="",
        help="e.g. https://blueairceramics.com (or set SHOPIFY_SHOP_ORIGIN)",
    )
    p.add_argument(
        "--buyer-json",
        default="",
        help="Path to JSON with email / shipping fields for checkout prefills",
    )
    p.add_argument(
        "--discount",
        default="",
        help="Optional discount code",
    )
    p.add_argument(
        "--shop-pay",
        action="store_true",
        help="Add payment=shop_pay to the permalink",
    )
    p.add_argument(
        "--require-available",
        action="store_true",
        help="Fail if the selected variant is not available",
    )
    p.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open the browser; only print the result",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print CheckoutResult as JSON (good for WPF subprocess capture)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    buyer: BuyerInfo | None = None
    if args.buyer_json:
        try:
            buyer = load_buyer_from_file(args.buyer_json)
        except Exception as exc:  # noqa: BLE001
            err = {"ok": False, "error": f"Failed to load buyer JSON: {exc}"}
            if args.json:
                print(json.dumps(err), flush=True)
            else:
                print(err["error"], file=sys.stderr)
            return 2
    else:
        buyer = BuyerInfo.from_env()

    result = open_checkout(
        args.product_url,
        quantity=args.quantity,
        variant_id=args.variant_id,
        buyer=buyer,
        shop_origin=args.shop_origin,
        open_browser=not args.no_open,
        require_available=args.require_available,
        discount=args.discount,
        shop_pay=args.shop_pay,
    )

    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False), flush=True)
    else:
        if result.ok:
            print(f"Product:  {result.product_title} ({result.handle})")
            print(f"Variant:  {result.variant_id} / {result.variant_title}")
            print(f"Available:{result.available}  Price: {result.price}")
            print(f"Checkout: {result.checkout_url}")
            if result.browser_opened:
                print("Browser:  opened")
            elif not args.no_open:
                print("Browser:  not opened — use the checkout URL manually")
            for w in result.warnings:
                print(f"Warning:  {w}", file=sys.stderr)
        else:
            print(f"Error: {result.error}", file=sys.stderr)

    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
