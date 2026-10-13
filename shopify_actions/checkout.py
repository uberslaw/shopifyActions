"""Resolve a Shopify product URL and open a prefilled cart permalink checkout."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional

USER_AGENT = "shopifyActions/1.0 (+personal checkout helper)"
DEFAULT_TIMEOUT_S = 15.0

# /products/{handle} with optional query/fragment; also accept bare handles.
_PRODUCT_PATH_RE = re.compile(
    r"^(?:https?://[^/]+)?(?:/[a-z]{2}(?:-[a-z]{2})?)?/products/([^/?#]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class BuyerInfo:
    """Optional checkout prefills (Shopify cart permalink query params)."""

    email: str = ""
    first_name: str = ""
    last_name: str = ""
    address1: str = ""
    address2: str = ""
    city: str = ""
    province: str = ""
    country: str = ""
    zip: str = ""
    phone: str = ""

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "BuyerInfo":
        e = env if env is not None else os.environ
        return cls(
            email=e.get("SHOPIFY_CHECKOUT_EMAIL", "").strip(),
            first_name=e.get("SHOPIFY_CHECKOUT_FIRST_NAME", "").strip(),
            last_name=e.get("SHOPIFY_CHECKOUT_LAST_NAME", "").strip(),
            address1=e.get("SHOPIFY_CHECKOUT_ADDRESS1", "").strip(),
            address2=e.get("SHOPIFY_CHECKOUT_ADDRESS2", "").strip(),
            city=e.get("SHOPIFY_CHECKOUT_CITY", "").strip(),
            province=e.get("SHOPIFY_CHECKOUT_PROVINCE", "").strip(),
            country=e.get("SHOPIFY_CHECKOUT_COUNTRY", "").strip(),
            zip=e.get("SHOPIFY_CHECKOUT_ZIP", "").strip(),
            phone=e.get("SHOPIFY_CHECKOUT_PHONE", "").strip(),
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "BuyerInfo":
        """Accept flat keys or nested shipping_address from a JSON config."""
        shipping = data.get("shipping_address")
        if isinstance(shipping, Mapping):
            src = {**data, **shipping}
        else:
            src = data

        def g(*keys: str) -> str:
            for k in keys:
                v = src.get(k)
                if v is not None and str(v).strip():
                    return str(v).strip()
            return ""

        return cls(
            email=g("email"),
            first_name=g("first_name", "firstName"),
            last_name=g("last_name", "lastName"),
            address1=g("address1", "address"),
            address2=g("address2"),
            city=g("city"),
            province=g("province", "state", "region"),
            country=g("country"),
            zip=g("zip", "postal_code", "postcode"),
            phone=g("phone"),
        )

    def as_query_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        if self.email:
            params["checkout[email]"] = self.email
        field_map = {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "address1": self.address1,
            "address2": self.address2,
            "city": self.city,
            "province": self.province,
            "country": self.country,
            "zip": self.zip,
            "phone": self.phone,
        }
        for key, value in field_map.items():
            if value:
                params[f"checkout[shipping_address][{key}]"] = value
        return params


@dataclass(frozen=True)
class ResolvedVariant:
    product_id: int
    product_title: str
    handle: str
    variant_id: int
    variant_title: str
    available: bool
    price: str
    product_url: str


@dataclass
class CheckoutResult:
    ok: bool
    checkout_url: str = ""
    product_url: str = ""
    handle: str = ""
    product_title: str = ""
    variant_id: int = 0
    variant_title: str = ""
    available: bool = False
    price: str = ""
    quantity: int = 1
    browser_opened: bool = False
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CheckoutError(Exception):
    """Raised for hard failures when raise_on_error=True."""


def _http_get_json(url: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise CheckoutError(f"HTTP {exc.code} fetching {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise CheckoutError(f"Network error fetching {url}: {exc.reason}") from exc
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckoutError(f"Invalid JSON from {url}") from exc


def parse_product_ref(product_url: str, default_origin: str = "") -> tuple[str, str]:
    """
    Return (origin, handle) from a product URL or handle.

    Examples:
      https://blueairceramics.com/products/cunt-mug-2
      /products/cunt-mug-2
      cunt-mug-2  (requires default_origin)
    """
    text = (product_url or "").strip()
    if not text:
        raise CheckoutError("product_url is empty")

    match = _PRODUCT_PATH_RE.match(text)
    if match:
        handle = urllib.parse.unquote(match.group(1))
        parsed = urllib.parse.urlparse(text if "://" in text else f"https://placeholder{text}")
        if parsed.scheme and parsed.netloc and parsed.netloc != "placeholder":
            origin = f"{parsed.scheme}://{parsed.netloc}"
        elif default_origin:
            origin = default_origin.rstrip("/")
        else:
            raise CheckoutError(
                "Relative product path needs a shop origin "
                "(pass full URL or set SHOPIFY_SHOP_ORIGIN)"
            )
        return origin, handle

    # Bare handle
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-]*", text):
        origin = (default_origin or os.environ.get("SHOPIFY_SHOP_ORIGIN", "")).rstrip("/")
        if not origin:
            raise CheckoutError(
                "Bare product handle requires full URL or SHOPIFY_SHOP_ORIGIN"
            )
        return origin, text

    raise CheckoutError(f"Could not parse Shopify product URL/handle: {product_url!r}")


def _pick_variant(
    product: Mapping[str, Any],
    *,
    variant_id: Optional[int] = None,
    prefer_available: bool = True,
) -> dict[str, Any]:
    variants = product.get("variants") or []
    if not variants:
        raise CheckoutError("Product has no variants")

    if variant_id is not None:
        for v in variants:
            if int(v["id"]) == int(variant_id):
                return v
        raise CheckoutError(f"Variant {variant_id} not found on product")

    if prefer_available:
        for v in variants:
            if v.get("available"):
                return v

    return variants[0]


def resolve_product(
    product_url: str,
    *,
    variant_id: Optional[int] = None,
    shop_origin: str = "",
    prefer_available: bool = True,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> ResolvedVariant:
    """Fetch product JSON and select a variant."""
    origin = shop_origin or os.environ.get("SHOPIFY_SHOP_ORIGIN", "")
    origin, handle = parse_product_ref(product_url, default_origin=origin)
    product_page = f"{origin}/products/{handle}"
    # .js returns the product object directly (no {product: ...} wrapper).
    data = _http_get_json(f"{product_page}.js", timeout_s=timeout_s)
    if not isinstance(data, dict) or "id" not in data:
        raise CheckoutError(f"Unexpected product payload for {handle}")

    variant = _pick_variant(
        data, variant_id=variant_id, prefer_available=prefer_available
    )
    return ResolvedVariant(
        product_id=int(data["id"]),
        product_title=str(data.get("title") or handle),
        handle=str(data.get("handle") or handle),
        variant_id=int(variant["id"]),
        variant_title=str(variant.get("title") or "Default Title"),
        available=bool(variant.get("available")),
        price=_format_price(variant.get("price")),
        product_url=product_page,
    )


def _format_price(raw: Any) -> str:
    """Shopify .js prices are often integer cents as string/int."""
    if raw is None:
        return ""
    if isinstance(raw, str) and "." in raw:
        return raw
    try:
        cents = int(raw)
        return f"{cents / 100:.2f}"
    except (TypeError, ValueError):
        return str(raw)


def build_cart_permalink(
    origin: str,
    variant_id: int,
    quantity: int = 1,
    *,
    buyer: Optional[BuyerInfo] = None,
    discount: str = "",
    shop_pay: bool = False,
    storefront_cart: bool = False,
) -> str:
    if quantity < 1:
        raise CheckoutError("quantity must be >= 1")
    base = f"{origin.rstrip('/')}/cart/{int(variant_id)}:{int(quantity)}"
    params: dict[str, str] = {}
    if buyer:
        params.update(buyer.as_query_params())
    if discount:
        params["discount"] = discount
    if shop_pay:
        params["payment"] = "shop_pay"
    if storefront_cart:
        params["storefront"] = "true"
    if not params:
        return base
    return f"{base}?{urllib.parse.urlencode(params)}"


def open_checkout(
    product_url: str,
    *,
    quantity: int = 1,
    variant_id: Optional[int] = None,
    buyer: Optional[BuyerInfo] = None,
    shop_origin: str = "",
    open_browser: bool = True,
    require_available: bool = False,
    prefer_available: bool = True,
    discount: str = "",
    shop_pay: bool = False,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    raise_on_error: bool = False,
) -> CheckoutResult:
    """
    Resolve product_url → variant, build cart permalink, optionally open browser.

    Stops at Shopify checkout / payment / MFA — does not submit payment.
    """
    warnings: list[str] = []
    try:
        resolved = resolve_product(
            product_url,
            variant_id=variant_id,
            shop_origin=shop_origin,
            prefer_available=prefer_available,
            timeout_s=timeout_s,
        )
        if require_available and not resolved.available:
            raise CheckoutError(
                f"Variant {resolved.variant_id} for {resolved.handle!r} is not available"
            )
        if not resolved.available:
            warnings.append(
                "Selected variant reports available=false; checkout may show sold out"
            )

        origin, _ = parse_product_ref(
            resolved.product_url,
            default_origin=shop_origin or os.environ.get("SHOPIFY_SHOP_ORIGIN", ""),
        )
        effective_buyer = buyer if buyer is not None else BuyerInfo.from_env()
        checkout_url = build_cart_permalink(
            origin,
            resolved.variant_id,
            quantity,
            buyer=effective_buyer,
            discount=discount,
            shop_pay=shop_pay,
        )

        browser_opened = False
        if open_browser:
            browser_opened = bool(webbrowser.open(checkout_url, new=2))
            if not browser_opened:
                warnings.append("webbrowser.open returned False; open checkout_url manually")

        return CheckoutResult(
            ok=True,
            checkout_url=checkout_url,
            product_url=resolved.product_url,
            handle=resolved.handle,
            product_title=resolved.product_title,
            variant_id=resolved.variant_id,
            variant_title=resolved.variant_title,
            available=resolved.available,
            price=resolved.price,
            quantity=quantity,
            browser_opened=browser_opened,
            warnings=warnings,
        )
    except CheckoutError as exc:
        if raise_on_error:
            raise
        return CheckoutResult(ok=False, product_url=product_url, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - surface to WPF as structured error
        if raise_on_error:
            raise
        return CheckoutResult(ok=False, product_url=product_url, error=str(exc))


def load_buyer_from_file(path: str) -> BuyerInfo:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, Mapping):
        raise CheckoutError("Buyer config must be a JSON object")
    return BuyerInfo.from_mapping(data)
