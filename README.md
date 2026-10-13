# shopifyActions

Python helper for a Windows WPF (or any) host: given a Shopify **product URL**, resolve the variant, build a **cart permalink** for quantity 1 (or N), prefill email/shipping when configured, and **open checkout in the default browser**.

Payment, Shop Pay, and MFA stay manual — this module only gets you to checkout as fast as possible.

Stdlib only (Python 3.10+). No `pip install` required.

## Quick start (Windows)

```bat
cd path\to\shopifyActions
checkout.cmd "https://blueairceramics.com/products/SOME-HANDLE" --buyer-json buyer.json --json
```

Or: `py -3 -m shopify_actions "..."` / `python -m shopify_actions "..."` (Python 3.10+ on PATH).

- Opens the system browser to Shopify checkout with the item in cart.
- `--json` prints a structured `CheckoutResult` on stdout for the WPF process to parse.
- `--no-open` builds the URL without launching a browser (useful for dry runs).

Copy [`buyer.example.json`](buyer.example.json) to `buyer.json` and fill in your details, **or** set the `SHOPIFY_CHECKOUT_*` variables from [`.env.example`](.env.example) in the process environment before calling Python.

## Call from WPF / Python

```python
from shopify_actions import open_checkout, BuyerInfo

result = open_checkout(
    "https://blueairceramics.com/products/cunt-mug-2",
    quantity=1,
    buyer=BuyerInfo.from_env(),  # or BuyerInfo(...), or load JSON
    open_browser=True,
    require_available=False,  # set True to abort when sold out
)

if result.ok:
    print(result.checkout_url)
else:
    print(result.error)
```

From C# you can shell out:

```csharp
// Example: capture JSON result
var psi = new ProcessStartInfo {
    FileName = "python",
    Arguments = "-m shopify_actions \"https://blueairceramics.com/products/HANDLE\" --buyer-json buyer.json --json",
    WorkingDirectory = @"C:\path\to\shopifyActions",
    RedirectStandardOutput = true,
    RedirectStandardError = true,
    UseShellExecute = false,
    CreateNoWindow = true,
};
```

Put this repo (or just the `shopify_actions` package folder + run from its parent) on `PYTHONPATH` / working directory so `python -m shopify_actions` resolves.

## CLI flags

| Flag | Meaning |
|------|---------|
| `product_url` | Full URL, `/products/{handle}`, or bare handle |
| `-q/--quantity` | Default `1` |
| `--variant-id` | Force a variant instead of first available |
| `--shop-origin` | Shop base URL if you only pass a handle |
| `--buyer-json` | Prefill file (see example) |
| `--require-available` | Exit nonzero if variant is sold out |
| `--shop-pay` | Append `payment=shop_pay` |
| `--no-open` | Do not launch browser |
| `--json` | Machine-readable result |

Exit code `0` = success, `1` = checkout build failed, `2` = bad buyer JSON.

## How it works

1. Parse origin + handle from the product URL you already capture.
2. `GET {origin}/products/{handle}.js` (public Shopify product JSON).
3. Pick the first **available** variant (or the forced `--variant-id`).
4. Build `https://{shop}/cart/{variant_id}:{qty}?checkout[email]=...&checkout[shipping_address][...]`.
5. `webbrowser.open(...)` on Windows uses the default browser.

Sold-out variants still produce a URL unless `--require-available` / `require_available=True` is set — Shopify may then show an empty/sold-out checkout.

## Assumptions

- **Runtime:** Python 3.10+ on PATH for the WPF host (`python` or `py -3`).
- **Network:** HTTPS to the shop origin (e.g. `blueairceramics.com`).
- **Permissions:** Ability to open the default browser for the interactive user session.
- **Scope:** One item toward checkout; no card entry, CAPTCHA, or MFA automation.

## Smoke test

```bat
python -m shopify_actions "https://blueairceramics.com/products/cunt-mug-2" --no-open --json
```

Expect `"ok": true` and a `checkout_url` containing `/cart/<variantId>:1`. Availability may be `false` between drops; that is normal.
