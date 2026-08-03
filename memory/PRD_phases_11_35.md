# BigFM — Phases 11-35 Monetization Expansion Backlog

> Parking lot. Captures the full long-term monetization roadmap on top of Phases 0-10. Each phase is incremental and additive — do not refactor away existing collections; build on top of them.

## Global rules for all phases 11-35
1. Do not replace existing architecture. All new monetization is incremental, additive modules built on top of Users / Businesses / Campaigns / Ads / Offers / Coupons / Rewards / SocialPassport / PlaybackLogs / Wallet / Orders / Appointments / Analytics.
2. Mobile-first. Every feature must work in the Expo mobile app.
3. Every monetization feature MUST track: impression, audio_completion, click, save, clip, share, lead, booking, purchase, redemption, check-in, repeat_visit, revenue, campaign_ROI, source_station, source_daypart, source_ad, source_ai_rj_segment, source_route_session.
4. Billing: integrate into existing Stripe subscriptions + checkout + advertiser invoices + prepaid budgets + SaaS plans + marketplace commissions + lead billing + booking billing + sponsorship billing + creator revenue share + merchant payouts (Stripe Connect later).
5. Privacy/compliance: clear "Sponsored" label, user opt-in for location targeting, notification prefs, privacy-safe analytics (no individual location history exposed to businesses), moderation for AI-generated content/shoutouts/ads, audit logs for advertiser actions, fraud prevention on coupons/rewards/redemptions.

## Suggested execution order (user-priority)
- Very High: 14, 15, 16, 17, 18, 21, 23, 27, 31, 32, 34
- High: 11, 12, 13, 19, 22, 25, 26, 28, 29, 35
- Medium-High: 30
- Medium: 20, 24, 33

## Best-MVP-first ordering (revenue acceleration)
1. Restaurant Passport SaaS (Ph 14)
2. Sponsored Games Marketplace (Ph 17)
3. Real-Time Boost Offers (Ph 16)
4. Transaction Marketplace (Ph 18)
5. Service Business Lead Generation (Ph 15)
6. AI Audio Ad Creator (Ph 34)
7. Retargeting Saved/Clipped Ads (Ph 32)
8. Merchant Loyalty Programs (Ph 27)
9. Event Promoter Tools (Ph 21)
10. White-Label AI Radio (Ph 23)

---

## Phase 11 — Sponsored AI RJ Personalities
Brand-sponsored AI RJ voices/personalities/dayparts/stations. Examples: "Lunch with RJ Priya, powered by Jay Bhavani", "Friday Night Club RJ, powered by Lava Lounge". Exclusivity rules by category and market.

Tables: `sponsored_rj_profiles` (id, name, description, personality_type, language, tone, voice_provider, voice_id, sample_audio_url, station_id, city, active) · `rj_sponsorships` (id, advertiser_id, business_id, rj_profile_id, station_id, city, daypart_id, category_exclusivity, start_date, end_date, sponsorship_fee, status) · `rj_mention_logs`.

## Phase 12 — Paid Featured Placement
Businesses pay to appear higher in lunch/dinner/route/nearby/event/"where to go tonight" recommendations. Bid models: flat monthly · CPM · CPC · CPS (save) · CPR (redemption). Always label "Sponsored".

Tables: `featured_placements` · `placement_impressions`.

## Phase 13 — Dynamic Sponsored Channels
Brands/events sponsor temp or permanent channels: Diwali Shopping Radio, Navratri Garba Radio, Movie Premiere Radio, Wedding Season Radio, Cricket Watch Party Radio, Date Night Radio, Restaurant Passport Radio. Includes sponsor reads, games, coupons, event promos, branded visuals.

Tables: `sponsored_channels` · `seasonal_channel_templates`.

## Phase 14 — Restaurant Passport SaaS (Very High)
Restaurants pay monthly to manage offers/prepaid meals/coupons/lunch campaigns/route ads/spin games/loyalty programs/QR redemption/birthday offers/slow-day boost. Tiers: Basic $99 · Growth $299 · Premium $799 · Enterprise custom.

Tables: `restaurant_saas_plans` · `restaurant_subscriptions` · `restaurant_menus` · `restaurant_menu_items` · `restaurant_redemption_logs`.

## Phase 15 — Service Business Lead Generation (Very High)
Lead-gen for dentists, doctors, salons, spas, med spas, auto repair, real estate, insurance, lawyers, accountants, tutors, gyms, wellness clinics, home services. Ad actions: Book / Callback / Save / Directions / Clip. Cost-per-lead + cost-per-booked-appointment billing.

Tables: `service_lead_campaigns` · `leads` · `lead_status_history` · `lead_billing_events`.

## Phase 16 — Real-Time "Boost Offer" Marketplace (Very High)
Businesses boost an offer when slow. E.g., 1:15pm "Boost 20% off lunch for next 90 min within 10 min". Objectives: impressions/saves/redemptions/directions/bookings/prepaid purchases. Delivered via RJ + route ad + lunch wheel + map + wallet reminder + push.

Tables: `boost_campaigns` · `boost_delivery_logs`.

## Phase 17 — Sponsored Games Marketplace (Very High)
Self-serve sponsored game campaigns: Spin & Win · Scratch Card · Guess the Song · Guess the Movie · Wheel of Fortune · Traffic Jam Trivia · Group Challenge · Mystery Box · Lucky Lunch Drop · Concert Ticket Raffle. Advertiser funds prizes + trigger rules. Group unlock rewards.

Tables: `sponsored_game_campaigns` · `sponsored_game_results` · `group_reward_challenges`.

## Phase 18 — Transaction Marketplace (Very High)
Prepaid meals, family bundles, dessert passes, tasting menus, gift cards, samplers, retail products, event packages, movie/concert tickets, club guest passes. Buy from ads/RJ/station/offers/wallet. Stripe checkout. Promo codes. QR redemption. Gift sending. Platform commission. Full attribution.

Tables: `marketplace_products` · `marketplace_orders` (source_ad_id, source_campaign_id, source_station_id, platform_fee, merchant_net) · `marketplace_order_items` · `gift_send_records`.

## Phase 19 — Premium Plus / VIP Passport Membership
Higher tier above Premium. Ad-free + exclusive giveaways + higher contest odds + early ticket access + monthly restaurant credit + birthday rewards + VIP badges + invite-only events + partner discounts + premium AI concierge + bonus reward multiplier + exclusive stations. Pricing: Premium $4.99-$7.99/mo, VIP Passport $14.99-$24.99/mo.

Tables: `membership_tiers` · `user_memberships` · `vip_benefits` · `vip_benefit_claims`.

## Phase 20 — Paid Social Passport Boosts (Medium)
Optional cosmetic/status upgrades: premium badge designs, profile themes, double-points weekend, premium event badge, friend-group challenge boost, birthday celebration package, personalized AI RJ shoutout, seasonal badge packs, VIP avatar frames. No pay-to-win.

Tables: `passport_boost_products` · `user_passport_boosts` · `passport_theme_assets`.

## Phase 21 — Event Promoter Tools (Very High)
Self-serve event promoter dashboard. Create event (concert/club/festival/movie/comedy/cultural/community). Upload creative. Sell tickets or link out. Sponsor countdown channel. Run giveaway. Target by city/genre/language/music taste/station/route/daypart. Event check-in badge.

Tables: `event_promoters` · `events` · `event_campaigns` · `event_giveaways` · `event_checkins`.

## Phase 22 — Movie Distributor and Theater Campaigns
Movie campaign pages, trailer audio ads, AI RJ movie buzz segments, ticket giveaways, showtime reminders, dinner+movie bundles, theater check-in badge, group movie night planning, movie trivia games. Indian releases + local theaters.

Tables: `movies` · `theaters` · `movie_showtimes` · `movie_campaigns` · `movie_giveaways`.

## Phase 23 — White-Label AI Radio for Venues (Very High)
B2B white-label for restaurants, hotels, gyms, malls, casinos, retail chains, apartment communities, office buildings, salons, temples, wedding venues. Branded radio + branded music + AI RJ + offers + birthday messages + loyalty + announcements. Revenue: setup fee + monthly SaaS + usage-based AI voice fee + add-ons + ad/reward package fee.

Tables: `white_label_stations` · `white_label_announcements` · `venue_playback_devices`.

## Phase 24 — Creator and Influencer Radio Channels (Medium)
Creator-hosted AI-assisted channels. AI helps generate RJ scripts in creator's approved style. Brand sponsorship + revenue share + referral links.

Tables: `creators` · `creator_channels` · `creator_sponsorships` · `creator_revenue_ledger`.

## Phase 25 — Local Business Data Dashboard
Privacy-safe business analytics: best performing offers, ad impressions, audio completions, coupon save rate, redemption rate, customer distance ranges, time-of-day perf, route conversion, weather-based perf, repeat visits, campaign ROI, wallet saves, clipped ads, booking perf, purchase perf, category benchmarks. CSV export. Premium analytics tier.

Tables: `business_analytics_reports` · `analytics_subscriptions`.

## Phase 26 — Sponsored Push Notifications
Opt-in sponsored push: lunch deal nearby, clipped ad reminder, coupon expiring soon, rainy day reward, concert ticket drop, movie giveaway, route reminder, saved offer reminder. Frequency caps. Quiet hours.

Tables: `push_campaigns` · `push_delivery_logs` · `user_notification_preferences`.

## Phase 27 — Merchant Loyalty Programs (Very High)
Merchant-owned loyalty: stamp cards, visit-based rewards, spend-based, birthday rewards, bring-friend rewards, lunch streak rewards. QR check-in, staff validation, Social Passport badges. Revenue: monthly loyalty software fee + redemption fee + CRM fee + campaign automation fee.

Tables: `merchant_loyalty_programs` · `user_loyalty_progress` · `loyalty_rewards_issued`.

## Phase 28 — Group Buying and Social Deals
Invite friends to unlock better deals. Tiers: 1=10% · 3=15% · 5=free appetizer · 10=VIP table. Group deal links + social lobby unlocks.

Tables: `group_deals` · `group_deal_sessions` · `group_deal_participants`.

## Phase 29 — AI Local Concierge Upsell
Concierge for Premium/VIP: "Where should I eat?", "Find a date night", "What's tonight?", "Lunch on my route?", "Plan dinner before this concert". Uses prefs + location + weather + time + route + Social Passport + wallet. Can book/buy/save/clip/get-directions. Sponsored results labeled.

Tables: `concierge_sessions` · `concierge_recommendations` · `concierge_sponsored_placements`.

## Phase 30 — Corporate/Campus/Hotel/Apartment Packages
Enterprise: private company radio · employee perks · campus event radio · resident passport · hotel guest entertainment · local merchant discounts · property-branded events · building announcements. Revenue: monthly licensing + setup fee + local sponsor revenue share + employee/resident perk package.

Tables: `organization_accounts` · `organization_members` · `organization_stations` · `organization_rewards`.

## Phase 31 — Seasonal Festival Monetization (Very High)
Navratri/Diwali/Holi/Eid/Cricket WC/Valentine/Mother's Day/NYE/Wedding Season packages. Admin creates festival; sponsors buy stations/games/coupons/events/badges. Users collect seasonal badges. Festival maps + event listings.

Tables: `seasonal_campaigns` · `seasonal_sponsors` · `seasonal_badges` · `user_seasonal_badge_progress`.

## Phase 32 — Ad Retargeting Based on Clipped Ads + Wallet Saves (Very High)
Triggers: clipped ad not bought · saved coupon not redeemed · viewed appointment not booked · gift card added to cart not bought · saved event not ticketed · route offer saved not visited · coupon expiring soon. Delivery: push, in-app, AI RJ reminder, email, SMS (with permission). Frequency caps.

Tables: `retargeting_campaigns` · `retargeting_audiences` · `retargeting_delivery_logs`.

## Phase 33 — Sponsored AI Shoutouts (Medium)
User/business submits shoutout (birthday/anniversary/restaurant table/event group/college club/wedding party/business-sponsored/concert attendee). AI generates script. Moderation. AI RJ reads on-air. Shareable clip. Revenue: $2.99-$9.99 user · business packages.

Tables: `shoutout_requests` · `shoutout_segments`.

## Phase 34 — AI Audio Ad Creator for Local Businesses (Very High)
Self-serve AI ad generation. Inputs: business name + offer + audience + language + tone + CTA + goal + duration. Outputs: 15/30s script · AI voiceover · display copy · coupon copy · RJ sponsor-read · push copy · translations. Preview/edit/voice select/A/B test.

Tables: `ai_ad_creator_projects` · `ai_ad_creatives` · `creative_ab_tests`.

## Phase 35 — Category Exclusivity
Premium exclusivity: exclusive dentist sponsor for Morning Drive · exclusive lunch sponsor for 12-2pm · exclusive club sponsor for Nightlife Mode · etc. Inventory by city/station/daypart/dates. Block conflicting campaigns. Waitlist for sold-out.

Tables: `category_exclusivity_inventory` · `category_exclusivity_purchases` · `exclusivity_conflict_logs`.

---

## Cross-cutting deliverables for Phases 11-35

**Admin screens to add:**
sponsorship management · featured placements · restaurant SaaS subs · service lead campaigns · boost campaigns · sponsored games · marketplace products · VIP memberships · event campaigns · movie campaigns · white-label stations · creator channels · seasonal campaigns · retargeting campaigns · shoutout approvals · AI ad creative approvals · exclusivity inventory.

**Advertiser dashboard tools:**
campaign creation · offer creation · appointment campaigns · product/gift card/prepaid meal creation · sponsored games · boost campaigns · analytics · billing · AI ad creation · lead management · booking management · redemption management.

**Listener app experiences:**
sponsored-but-labeled recommendations · action cards during ads · ad clipping · wallet saves · marketplace purchases · appointment booking · Social Passport boosts · VIP membership upgrades · event saves · group deals · concierge recommendations · shoutout purchases · seasonal badges.


---

# Beyond Phase 35 — keep appending here as new phases come in.

## Phase 36 — Podcast Creator Network + Social Podcasting

On-demand creator-driven audio alongside existing non-interactive music radio (Phases 1-8) and Talk Stations (Phase 9). Separate content rules, licensing, ads, analytics, monetization.

### Content type taxonomy (now 3 surfaces)
1. AI Music Radio Stations — personalized non-interactive
2. AI Talk Stations — scheduled AI/news/talk
3. Creator Podcast Channels — user/creator-uploaded or AI-assisted

### Creator Studio
Create channel · episode upload · in-browser/in-app recorder · cover art · title/description/show notes · categories/tags · language · city · sponsor slots · shoppable cards · coupons/offers · appointment links · product/gift card links · schedule publish · save draft · submit for approval · unpublish · analytics.

### AI Podcast Builder
Episode outline · intro/outro script · sponsor-read script · title options · show notes · chapter markers · transcript · clean transcript (filler removal) · short clips · social captions · email/push copy · long-audio summary · multi-language translation · AI voice intro/outro · branded sponsor-read audio.

### Listening features
Browse · follow · play · save · share · comment · emoji reactions · report · create listening room · ask creator a question · bookmark clips · add sponsor offer to wallet · buy product · book appointment · join giveaway.

### Social features
Creator profile · followers · listener comments · creator Q&A inbox · episode discussion rooms · live premiere listening rooms · creator badges · fan badges · top-listener badges · shareable podcast clips · Social Passport integration.

### Monetization
Pre/mid/post-roll ads · AI-read sponsor ads · creator sponsorships · paid featured placement · paid episode boosts · premium subscriber-only episodes · creator tipping · paid creator communities · affiliate links · shoppable product cards · coupon cards · appointment booking cards · event ticket cards · gift card cards · restaurant prepaid meal cards · creator revenue share.

### Categories
local food · real estate · business · health & wellness · movies & entertainment · sports · nightlife · events · community · faith & culture · education · finance · legal · comedy · interviews · news commentary.

### Creator approval workflow
Apply → admin approve → admin sets monetization eligibility + revenue share % → admin may require pre-publish review → admin moderation tools (disable comments, remove content, mark sponsored, review AI sponsor reads, enforce disclosure labels).

### Ad system
Creators insert pre/mid/post ad slots. Ads matched by category + city + language + audience + sponsor relevance. Direct sponsorship of creator channel. Platform-sold ads. Creator-sold sponsor reads (with admin approval). Host-read style AI sponsor messages. Track impressions/completions/clicks/saves/purchases/bookings/redemptions.

### Shoppable cards during playback (synced to timeline)
Save Coupon · Clip This Segment · Buy Product · Buy Gift Card · Book Appointment · Reserve Table · Buy Ticket · Join Giveaway · Add Offer to Wallet · Get Directions · Request Callback · Share Clip.

### Clipping
Users clip episode segments → shareable, can include sponsor cards, attribution tracked. Creators can publish "official clips".

### Analytics
**Creator dashboard:** plays · unique listeners · completion rate · avg listen duration · followers · comments · shares · clips created · ad revenue · sponsor revenue · coupon saves · purchases · bookings · redemptions · top cities · top episodes · listener growth.
**Admin dashboard:** total podcast plays · creator performance · revenue by creator · ad fill · top categories · reported content · pending approvals · sponsored content disclosures · platform commission.

### Schema
```
podcast_creators { _id, user_id, display_name, bio, city, language, category,
                    profile_image_url, social_links_json, approval_status,
                    monetization_enabled, revenue_share_percent, created_at }
podcast_channels { _id, creator_id, title, description, category, language, city,
                    cover_image_url, explicit_flag, subscriber_only, active, created_at }
podcast_episodes { _id, channel_id, creator_id, title, description, audio_url,
                    cover_image_url, duration_seconds, transcript_text, show_notes,
                    language, category, tags_json, publish_status,
                    scheduled_publish_time, published_at, approval_status,
                    explicit_flag, subscriber_only, created_at }
podcast_episode_chapters { _id, episode_id, title, start_time_seconds,
                            end_time_seconds, summary }
podcast_ad_slots { _id, episode_id, slot_type (pre|mid|post),
                    start_time_seconds, duration_seconds,
                    ad_id, campaign_id, sponsor_business_id, status }
podcast_sponsor_reads { _id, episode_id, sponsor_business_id, script_text,
                         audio_url, disclosure_text, approval_status, created_at }
podcast_action_cards { _id, episode_id, start_time_seconds, end_time_seconds,
                        card_type, title, description, offer_id, product_id,
                        appointment_service_id, event_id, destination_url, active }
podcast_clips { _id, episode_id, creator_id, user_id,
                 start_time_seconds, end_time_seconds, title,
                 clip_audio_url, transcript_text, share_url,
                 sponsor_card_id, created_at }
podcast_comments { _id, episode_id, user_id, comment_text, parent_comment_id,
                    status, created_at }
podcast_follows { _id, user_id, channel_id, followed_at }
podcast_episode_saves { _id, user_id, episode_id, saved_at }
podcast_analytics_events { _id, user_id, episode_id, channel_id, creator_id,
                            event_type, position_seconds, ad_id, action_card_id, created_at }
creator_payouts { _id, creator_id, period_start, period_end,
                   gross_revenue, platform_fee, creator_net,
                   payout_status, paid_at }
podcast_moderation_reports { _id, episode_id, comment_id, reporter_user_id,
                              reason, status, reviewed_by, created_at }
```

### Integration
Object storage for audio + art · OpenAI for transcripts/summaries/titles/show-notes/ad copy · ElevenLabs for AI intros/outros + sponsor reads · Stripe (incl. Connect) for subs/tips/premium episodes/payouts · Phase 10 wallet/coupon/product/appointment/event/marketplace for shoppable cards · Phase 7 notifications for new-episode alerts · admin moderation for comments/uploads/sponsor disclosures.

### MVP scope
1. Creator application + approval
2. Podcast channel creation
3. Episode upload (file + cover art)
4. Episode playback (with synced action cards)
5. Follow creator
6. Save episode
7. Comments
8. AI-generated title/description/show notes (one-click)
9. Sponsor/action card attachment timeline
10. Basic analytics (plays/completions/followers)
11. Admin moderation queue
12. Creator dashboard

### Out of scope for Phase 36 MVP
- Live premieres (uses Phase 7 lobby infra)
- Multi-host in-app recording (upload pre-mixed audio for now)
- Video podcast (audio only)
- Creator Stripe Connect onboarding (manual payouts initially)


## Phase 37 — Podcast Syndication + Multi-Platform Distribution

Extends Phase 36 so creators can syndicate to external podcast platforms via standards-compliant RSS feeds.

### Supported external platforms (priority order)
Apple Podcasts · Spotify for Podcasters · Amazon Music/Audible · YouTube Music / YouTube Podcasts · iHeartRadio · Pandora · TuneIn · Pocket Casts · Deezer · Podcast Index · Listen Notes · Castbox · Overcast · Player FM · any RSS.com-compatible · any other RSS-compatible podcast app.

### Core features
1. Generate RSS feed per channel (Atom + RSS 2.0 + iTunes/Apple + Spotify + Podcast Index `podcast:` namespace)
2. Host audio + cover art (existing object storage, byte-range enclosures w/ accurate Content-Length)
3. All required RSS metadata
4. Apple Podcasts namespace tags (itunes:author/category/explicit/image/duration/episodeType/season/episode/owner/...)
5. Spotify-compatible metadata
6. Episode GUIDs (stable, unique, never reused)
7. Episode enclosure URLs (audio_url + size + mime_type)
8. duration · file_size · mime_type · publish date · explicit flag · language · author · category · description
9. Show-level artwork (3000x3000 PNG/JPG required for Apple)
10. Episode-level artwork
11. Trailer episodes
12. Season + episode numbers
13. Episode types: full / trailer / bonus
14. Transcript links (Podcast Index `podcast:transcript`, JSON or SRT)
15. Creator ownership email
16. Copyright field
17. Public podcast website page
18. RSS feed validation (Apple Podcasts + W3C RSS + Podcast Index)
19. Feed preview (HTML preview before publish)
20. Manual refresh / regeneration
21. 301 redirect support for feed migration
22. Import from existing RSS feed (creator already has podcast elsewhere)

### Creator Distribution Dashboard (new "Distribution" tab)
RSS Feed URL card + Copy + Validate · Platform submission checklist (per-platform status `not_submitted|submitted|approved|rejected|needs_action`) · Paste-in fields for Apple/Spotify/YouTube/Amazon/other approved URLs · "Published externally" badges · Import existing RSS · Distribution settings (publish-to-RSS toggle, owner name/email, copyright, default explicit/language/category) · Copyright confirmation checkbox required.

### Publishing flow
1. Creator uploads/records episode (Phase 36)
2. Enters metadata + artwork + season + episode number
3. Picks destination: `internal_only` | `internal_and_rss` | `scheduled`
4. If RSS → regenerate channel RSS feed (cache-bust ETag/Last-Modified)
5. Notify subscribed platforms via WebSub/PubSubHubbub ping where supported
6. Track external platform show links once creator pastes them after approval

### Schema
```
podcast_feeds { _id, channel_id, feed_url, rss_xml_url, feed_status,
                 last_generated_at, last_validated_at, validation_errors_json,
                 redirect_url, active }
podcast_platform_submissions { _id, channel_id, platform_name, platform_status,
                                submission_url, platform_show_url,
                                submitted_at, approved_at, rejected_at,
                                rejection_reason, notes }
podcast_external_links { _id, channel_id, platform_name, platform_show_url, active, created_at }
podcast_feed_imports { _id, creator_id, source_feed_url, import_status,
                        imported_channel_id, imported_episode_count,
                        error_log_json, created_at }
podcast_distribution_settings { _id, channel_id, publish_to_rss,
                                 allow_external_distribution, owner_name,
                                 owner_email, copyright_text,
                                 default_explicit_flag, default_language,
                                 default_category, created_at }
podcast_episode_distribution { _id, episode_id, channel_id,
                                publish_to_internal_app, publish_to_rss,
                                rss_guid, external_status, published_to_feed_at }
feed_validation_logs { _id, feed_id, validation_status,
                        validation_errors_json, checked_at }
podcast_rss_downloads { _id, episode_id, channel_id, user_agent, ip_hash,
                         platform_detected, country, region, downloaded_at }
podcast_directory_clicks { _id, channel_id, platform_name, user_id, clicked_at }
```

### Admin controls
Approve external distribution · disable RSS on policy violation · review show metadata + explicit + copyright ownership · review uploaded music / copyrighted audio risk · force regenerate · set feed redirect · remove episode from feed · view submission statuses.

### Creator controls
Enable/disable RSS · copy feed URL · validate feed · view submission instructions · store platform links · import existing RSS · export feed · migrate via 301 redirect · view feed health.

### Content + copyright rules
Creator must confirm rights to all audio/music/clips/artwork. Strong warning against copyrighted music unless licensed. Background music must be royalty-free or licensed. Content policy checkbox required to enable RSS distribution. Takedown workflow + DMCA intake route.

### Analytics
RSS feed download counts + last-download timestamp · episode enclosure download counts · user-agent parsing for platform breakdown (Apple/Spotify/Overcast/Pocket Casts...) · country/region (GeoIP) · referral source where available (Spotify) · external link click tracking ("Listen on Apple/Spotify/..." buttons from public page) · platform URLs from creator as outbound link analytics.

### Public podcast pages (SEO + OG)
`/p/<channel_slug>` — embedded player + episode list + "Listen on Apple/Spotify/Amazon/YouTube/RSS" buttons. `/p/<channel_slug>/<episode_slug>` — embedded player + transcript + chapters + show notes + shoppable cards from Phase 36. OG + Twitter Card meta tags.

### MVP scope
1. Valid RSS feed per channel (passes Apple + Podcast Index validators)
2. Publish episode to internal app AND RSS feed
3. Copyable RSS feed URL in Creator Studio
4. Platform submission checklist with status tracking
5. Store external platform links once approved
6. Validate required metadata before RSS publish allowed
7. RSS download analytics (counts + user-agent platform detection)
8. Admin ability to disable feed
9. Creator copyright confirmation gate
10. Import existing RSS feed (one-shot migration)

### UI work
"Distribution" tab in Creator Studio (Phase 36): RSS Feed URL card · Copy · Validate · Platform checklist · Submission status table · External platform links · Import existing feed · Distribution settings · Copyright confirmation. Public show + episode pages with 5 "Listen on X" buttons.

### Out of scope for Phase 37 MVP
- Automated submission via platform APIs (most aren't public)
- WebSub real-time push beyond a basic ping
- Spotify deeper analytics ingestion
- Multi-tenant feed branding (single brand for now)
