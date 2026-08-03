# Phase 42 — Ad Stack Audit + Session Plan

> **Status**: AUDIT ONLY. No Phase 42 code yet.
> **Anchor**: HEAD = post-Phase 41 P0/P1/P2 commits.

## 0. Scope (user spec)

1. Banner ads throughout the app on **free tier** only
2. Admin can toggle **Google AdSense** for unsold-inventory backfill
3. Admin can configure **SSPs**: Magnite, PubMatic, Index Exchange, Triton Digital (audio), AdsWizz (audio)
4. Waterfall fallback: direct sold → AdSense → SSP cascade → house ads
5. Audio breaks: **drive time** = 2 breaks/hour, **5 minutes each**; non-drive-time = standard 1–2 minute breaks
6. Both audio + banner SSP integrations

## 1. Existing ads infrastructure (significant — DO NOT rebuild)

### Backend services already shipped
| Service | Role | Phase 42 reuse |
|---|---|---|
| `services/ad_decisioning.py` | Per-listener ad selection w/ frequency cap + targeting | ✅ Wrap as the **direct-sold tier** of the waterfall |
| `services/delivery.py` | Tracking pixels, impression logging | ✅ Reuse for all tiers |
| `services/gam_adapter.py` + `gam_client.py` | Google Ad Manager (currently mocked — see boot log `integration=gam creds missing → mock`) | ✅ **Promote to live** for AdSense + GAM Direct |
| `services/route_ad_engine.py` | `route_ad_opportunities` collection — commute-aware insertion points | ✅ Already implements drive-time detection via Phase 39 location data |
| `services/ads_txt_manager.py` | ads.txt / app-ads.txt config | ✅ Reuse — already there |
| `services/vast_wrapper.py` | VAST 3/4 wrapper | ✅ Critical for audio SSP integration |
| `services/ssp_adapters/` directory | Pre-wired SSP adapter framework | ✅ Just needs concrete adapters per SSP |
| `services/freq_caps.py` | Per-user frequency caps | ✅ Reuse |
| `services/imaging_*.py` | Banner creative validation + resizing | ✅ Reuse for banner tier |
| `services/ai_ad_creator.py` | AI-generated banner/audio creatives | ✅ House-ad backfill tier |

### Existing routes
- `routes/ads_public.py` — listener-facing ad endpoints (`/api/ads/next_audio`, etc.)
- `routes/admin_ads.py` — admin queue + creative review
- `routes/advertiser.py` — advertiser portal (campaigns, line items)
- `routes/advertiser_aggregate.py` — Phase 39 S7 aggregate analytics

### Existing collections
- `ad_campaigns`, `ad_creatives`, `ad_line_items`, `ad_impressions`, `route_ad_opportunities`, `freq_caps_state`, plus the Phase 18 pacing / programmatic tables.

**Verdict**: ~70% of Phase 42 is **integration & admin config UI** on top of existing infra. Net-new code is mostly: AdSense/SSP concrete adapters, banner tier UI, waterfall orchestrator, and the drive-time pod scheduler.

## 2. Proposed session breakdown — 6 sessions

### Session 1 — Waterfall orchestrator + banner ad slots (free tier)
- New `services/ad_waterfall.py` — orchestrates direct-sold → AdSense → SSP cascade → house
- Banner slots in: Home, Radio player, Games, Wallet, Trivia (5 slot IDs)
- React `<BannerAdSlot slot_id="home_top" />` component that calls `GET /api/ads/banner/:slot_id`
- Free-tier gate: premium users (`is_premium=True`) skip banner fetch entirely
- **Gates**: 5 slot rendering on free user; 0 slot rendering on premium; waterfall logs which tier filled

### Session 2 — Google AdSense integration (banner backfill)
- Admin UI `/admin/ads/adsense` to paste publisher ID + slot mappings
- `services/adsense_adapter.py` → renders `<ins class="adsbygoogle">` for unsold slots
- ads.txt entry auto-added when AdSense enabled
- **Gates**: admin can enable/disable AdSense at runtime; ads.txt reflects state

### Session 3 — Drive-time audio break scheduler
- Extend `services/route_ad_engine.py` — when user's `daypart` is morning-rush (7-9am local) or evening-rush (5-7pm local), schedule **2 breaks per hour, 5 min each**
- Outside drive time: 1-2 min breaks every ~15 min (existing behavior)
- `services/break_pod.py` — builds a "pod" of 3-5 audio ads stitched to fill the 5-min slot
- **Gates**: simulated morning-rush listener gets 2×5min pods/hour; off-peak gets 1×90s breaks

### Session 4 — SSP audio adapters (AdsWizz + Triton)
- VAST 4 endpoints for both
- Bid request via OpenRTB 2.5 (audio sub-spec)
- Multi-bid waterfall: parallel bid request → highest CPM wins → fallback to next
- Timeout: 800ms per bidder (industry standard)
- **Gates**: admin can enable each SSP; live VAST URL returns playable creative

### Session 5 — SSP banner adapters (Magnite + PubMatic + Index Exchange)
- Standard OpenRTB 2.5 display bid requests
- Prebid.js-style header-bidding client integration (server-side wrapper, no JS lib needed)
- **Gates**: admin enables each; banner slot fills from highest bidder

### Session 6 — Admin SSP config UI + reporting + Phase 42 closure
- `/admin/ads/ssps` page: 5 SSP cards (Magnite, PubMatic, Index, Triton, AdsWizz) with credentials, eCPM floor, enable toggle, daily impression cap
- Live waterfall report: per-tier fill rate, eCPM, revenue
- Reporting: hourly cron rolls `ad_impressions` → `ad_revenue_daily` with tier attribution
- **Gates**: admin sees fill rate, eCPM, revenue per SSP per day; export CSV

## 3. Blockers / decisions for user

| # | Decision | Recommendation |
|---|---|---|
| 1 | Which SSP first? | **AdsWizz** (audio, since 5-min drive-time pods are core spec) + **GAM/AdSense** (banner unsold backfill) |
| 2 | OpenRTB version | **2.5** (industry default; 2.6 not yet broadly supported by audio SSPs) |
| 3 | App-ads.txt vs ads.txt | Both. Web → ads.txt at site root; mobile (when shipped) → app-ads.txt at developer site root. Already handled by `ads_txt_manager.py` |
| 4 | Publisher onboarding for AdSense | User must apply for AdSense publisher account — flag this **2-3 weeks** of lead time |
| 5 | SSP credentials format | Each SSP has its own dashboard for getting `seller_id` / `publisher_id` / endpoint URL — admin UI just stores them, no auto-provision |
| 6 | Default eCPM floor | $0.50 audio, $0.20 banner — admin editable |
| 7 | Free-tier ad density cap | Cap banner ads at 1 per page; cap audio at 2 breaks/hr drive-time, 4 breaks/hr off-peak. Industry standard. |

## 4. Risk register

| Risk | Mitigation | Session |
|---|---|---|
| AdSense publisher account rejection (no traffic) | Apply ASAP in parallel with Sessions 1–3; ship without AdSense, add when approved | Pre-Session 2 |
| SSP eCPM too low to be worth integration cost | Set $0.50 audio / $0.20 banner floor; if all SSPs decline, waterfall to house ads | Session 4-5 |
| OpenRTB bid timeouts cause silent gaps | 800ms timeout per bidder, 2s total waterfall budget, fallback to house | Session 1 |
| ads.txt entries wrong → SSP suspends account | `ads_txt_manager.py` auto-regenerates on SSP enable/disable | Sessions 2, 4, 5 |
| Drive-time misdetection (consent < 3) → no audio pod | Falls back to off-peak schedule for those users | Session 3 |

## 5. Estimated Phase 42 MVP cost

- **6 sessions**, sequenced. Sessions 4 + 5 can parallelize if needed (audio vs banner SSPs are independent).
- **Lead time blocker**: AdSense publisher application (~2-3 weeks) — start NOW, before Session 1 ships.

## 6. Key reuse callouts

1. `services/gam_adapter.py` — promote from mock to live (admin toggle exists)
2. `services/route_ad_engine.py` — drive-time pod scheduling builds on this
3. `services/vast_wrapper.py` — audio SSPs all speak VAST
4. `services/ad_decisioning.py` — direct-sold tier of the waterfall (NO rewrite needed)
5. `services/freq_caps.py` — caps apply uniformly across all waterfall tiers

## 7. Halt — awaiting user decisions

The 7 decisions in §3. The biggest is the AdSense publisher application
(~2-3 weeks lead time) — start that NOW, in parallel with Sessions 1-3.
