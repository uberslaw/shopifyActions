"""Stdlib unit tests (no network): python3 tests/test_checkout_unit.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shopify_actions.checkout import (  # noqa: E402
    BuyerInfo,
    CheckoutError,
    build_cart_permalink,
    parse_product_ref,
)


class ParseProductRefTests(unittest.TestCase):
    def test_full_url(self) -> None:
        origin, handle = parse_product_ref(
            "https://blueairceramics.com/products/cunt-mug-2?variant=1"
        )
        self.assertEqual(origin, "https://blueairceramics.com")
        self.assertEqual(handle, "cunt-mug-2")

    def test_localized_path(self) -> None:
        origin, handle = parse_product_ref(
            "https://blueairceramics.com/en-gb/products/cunt-mug-2"
        )
        self.assertEqual(handle, "cunt-mug-2")
        self.assertEqual(origin, "https://blueairceramics.com")

    def test_bare_handle_needs_origin(self) -> None:
        with self.assertRaises(CheckoutError):
            parse_product_ref("cunt-mug-2")
        origin, handle = parse_product_ref(
            "cunt-mug-2", default_origin="https://blueairceramics.com"
        )
        self.assertEqual(origin, "https://blueairceramics.com")
        self.assertEqual(handle, "cunt-mug-2")


class PermalinkTests(unittest.TestCase):
    def test_builds_prefilled_url(self) -> None:
        buyer = BuyerInfo(email="a@b.com", city="Belfast", country="GB")
        url = build_cart_permalink(
            "https://blueairceramics.com",
            50849473888597,
            1,
            buyer=buyer,
        )
        self.assertTrue(url.startswith("https://blueairceramics.com/cart/50849473888597:1?"))
        self.assertIn("checkout%5Bemail%5D=a%40b.com", url)
        self.assertIn("checkout%5Bshipping_address%5D%5Bcity%5D=Belfast", url)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
