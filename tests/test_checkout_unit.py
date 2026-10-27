"""Stdlib unit tests (no network): python3 tests/test_checkout_unit.py"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shopify_actions.checkout import (  # noqa: E402
    BuyerInfo,
    CheckoutError,
    WEDNESDAY_TEXT_POSITIONS,
    WEDNESDAY_WAIT_VALUE,
    build_cart_permalink,
    open_checkout,
    parse_product_ref,
    wednesday_cart_properties,
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
        self.assertNotIn("properties%5B", url)

    def test_wednesday_properties_keep_bss_spaces(self) -> None:
        position = "Small text inside (max 48 characters)"
        buyer = BuyerInfo(
            email="a@b.com",
            text_position=position,
            mug_message="Hello",
            left_handed_handle="No",
            additional_information="Leave by the side door",
            agree_wait_time=True,
        )
        properties, missing = wednesday_cart_properties(buyer)
        self.assertEqual(missing, [])
        self.assertEqual(properties[" Text position"], position)
        self.assertEqual(properties[" your chosen message "], "Hello")
        self.assertTrue(properties[" Custom mugs take 8 weeks to make"].endswith(" "))
        self.assertEqual(properties[" Left handed handle?"], "No")
        url = build_cart_permalink(
            "https://blueairceramics.com",
            51707588542805,
            1,
            buyer=buyer,
            properties=properties,
            shop_pay=True,
        )
        self.assertIn("properties%5B%20Text%20position%5D=Small%20text%20inside%20%28max%2048%20characters%29", url)
        self.assertIn("properties%5B%20your%20chosen%20message%20%5D=Hello", url)
        self.assertIn("properties%5B%20Left%20handed%20handle%3F%5D=No", url)
        self.assertTrue(url.split("properties%5B%20Custom%20mugs%20take%208%20weeks%20to%20make%5D=", 1)[1].split("&", 1)[0].endswith("%20"))
        self.assertIn("payment=shop_pay", url)
        self.assertNotIn("4242", url)

    def test_incomplete_wednesday_options_send_nothing(self) -> None:
        buyer = BuyerInfo.from_mapping(
            {
                "email": "a@b.com",
                "postcode": "BT1 1AA",
                "address": "1 High Street",
                "card_number": "4242424242424242",
                "cvv": "123",
                "password": "secret",
                "wednesday": {
                    "text_position_choices": list(WEDNESDAY_TEXT_POSITIONS),
                    "text_position": "",
                    "message": "",
                    "left_handed_handle": "",
                    "additional_information": "",
                    "agree_wait_time": True,
                },
            }
        )
        self.assertEqual(buyer.zip, "BT1 1AA")
        self.assertEqual(buyer.address1, "1 High Street")
        self.assertTrue(buyer.agree_wait_time)
        params = buyer.as_query_params()
        self.assertNotIn("4242", str(params))
        self.assertNotIn("secret", str(params))
        properties, missing = wednesday_cart_properties(buyer)
        self.assertEqual(properties, {})
        self.assertEqual(missing, ["text_position", "message", "left_handed_handle"])
        url = build_cart_permalink("https://blueairceramics.com", 1, buyer=buyer, properties=properties)
        self.assertNotIn("properties%5B", url)
        self.assertIn(WEDNESDAY_WAIT_VALUE, "I agree to the wait time. I have adhered to the rules with my text request. ")


class SuppliedVariantTests(unittest.TestCase):
    PRODUCT = {
        "id": 1,
        "title": "Mug",
        "handle": "cunt-mug-2",
        "variants": [{"id": 50849473888597, "title": "Default Title", "available": True, "price": 3800}],
    }

    def test_variant_id_skips_product_fetch(self) -> None:
        with mock.patch(
            "shopify_actions.checkout._http_get_json",
            side_effect=AssertionError("product should not be fetched"),
        ), mock.patch("shopify_actions.checkout.webbrowser.open") as opened:
            result = open_checkout(
                "https://blueairceramics.com/products/cunt-mug-2",
                quantity=2,
                variant_id=50849473888597,
                buyer=BuyerInfo(email="a@b.com"),
                shop_pay=True,
                open_browser=False,
            )
        opened.assert_not_called()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.variant_id, 50849473888597)
        self.assertEqual(result.handle, "cunt-mug-2")
        self.assertFalse(result.available)
        self.assertTrue(
            result.checkout_url.startswith("https://blueairceramics.com/cart/50849473888597:2?")
        )
        self.assertIn("payment=shop_pay", result.checkout_url)
        self.assertIn("checkout%5Bemail%5D=a%40b.com", result.checkout_url)
        self.assertTrue(any("not fetched" in w for w in result.warnings))

    def test_require_available_still_fetches(self) -> None:
        with mock.patch(
            "shopify_actions.checkout._http_get_json", return_value=self.PRODUCT
        ) as fetched:
            result = open_checkout(
                "https://blueairceramics.com/products/cunt-mug-2",
                variant_id=50849473888597,
                buyer=BuyerInfo(),
                require_available=True,
                open_browser=False,
            )
        fetched.assert_called_once()
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.available)
        self.assertEqual(result.price, "38.00")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
