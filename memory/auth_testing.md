# Auth Testing Guide — Phase 39M.2

## Playwright Login Flow
```python
await page.goto("http://localhost:3001/login")
await page.wait_for_timeout(15000)
email = page.locator('input[placeholder="you@example.com"]')
pw = page.locator('input[placeholder="Password"]')
await email.fill('demo@bigfm.dubai')
await pw.fill('DemoPass123!')
await page.wait_for_timeout(300)
sign_in = page.locator('div:has-text("Sign in")').last
await sign_in.click(force=True)
await page.wait_for_timeout(8000)
```

## Wallet Verification
```python
await page.goto("http://localhost:3001/wallet")
await page.wait_for_timeout(5000)
# Should see balance, tier, action buttons (Scan to Pay, My Splits, Deals)
```

## Scan-to-Pay (Web)
```python
await page.goto("http://localhost:3001/scan-to-pay")
# Web shows manual entry. Enter stq_ token and click Continue.
```

## My Splits
```python
await page.goto("http://localhost:3001/my-splits")
# Shows All/Pending/Paid/Expired filter + split cards
```

## Coupon Detail
```python
await page.goto("http://localhost:3001/coupon/cpn_e1dcd5803d774e")
# Shows QR code + offer details + redeem button
```

## Key testIDs
| Element | testID |
|---------|--------|
| Wallet scan-to-pay | `wallet-scan-to-pay-btn` |
| Wallet my-splits | `wallet-my-splits-btn` |
| Wallet deals | `wallet-deals-btn` |
| Manual token input | `manual-token-input` |
| Manual submit | `manual-submit-btn` |
| Camera permission | `camera-perm-btn` |
| Pay submit | `pay-submit-btn` |
| Split bill | `split-bill-btn` |
| Pay receipt title | `pay-receipt-title` |
| Pay bigcoin earned | `pay-bigcoin-earned` |
| Pay done | `pay-done-btn` |
| My splits title | `my-splits-title` |
| Splits filter | `splits-filter-{all|pending|paid|expired}` |
| Coupon redeem | `coupon-redeem-btn` |
| Coupon directions | `coupon-get-directions` |
