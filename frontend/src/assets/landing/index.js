// Phase STATIC.BOOT.v2 (2026-08-01) — landing/marketing hero images
// bundled INTO the frontend build so they ship as part of the JS
// bundle with content-hashed filenames.
//
// Before: `useMarketingAssets()` fetched `/api/marketing/assets` and
// resolved image URLs against `REACT_APP_BACKEND_URL/api/static/...`.
// If the backend static files weren't shipped to prod (git-drift, an
// aggressive `.dockerignore`, or a missing seed run) the images
// silently 404'd and users saw empty cards.
//
// After: these imports are compiled into the frontend bundle by
// webpack.  Each PNG becomes a fingerprinted asset at build time.
// The bundle guarantees the image exists — prod cannot "lose" it
// without a full re-deploy that would fail for other reasons.
//
// The `useMarketingAssets` hook prefers these bundled URLs over the
// API-provided ones so the API/DB stays authoritative for CMS-driven
// keys but never blocks the six flagship marketing hero images
// (`live_trivia`, `game_campaigns`, `coupon_wallet`, `audio_ads`,
// `sponsored_games`, `route_based_ads`) or the mobile-hero splash
// (`mobile_hero`).

import audio_ads              from "./audio_ads.png";
import coupon_wallet        from "./coupon_wallet.png";
import game_campaigns    from "./game_campaigns.png";
import game_default          from "./game_default.png";
import game_lucky_draw    from "./game_lucky_draw.png";
import game_lyric_hunt    from "./game_lyric_hunt.png";
import game_music_trivia    from "./game_music_trivia.png";
import game_predict_win    from "./game_predict_win.png";
import game_scratch_card from "./game_scratch_card.png";
import game_spin_wheel    from "./game_spin_wheel.png";
import live_reporting        from "./live_reporting.png";
import live_trivia              from "./live_trivia.png";
import mobile_hero            from "./mobile_hero.png";
import promo_community_radio  from "./promo_community_radio.png";
import promo_trivia_rewards    from "./promo_trivia_rewards.png";
import promo_try_chat            from "./promo_try_chat.png";
import route_based_ads    from "./route_based_ads.png";
import sponsored_games    from "./sponsored_games.png";

export const LANDING_IMAGES = {
  audio_ads,
  coupon_wallet,
  game_campaigns,
  game_default,
  game_lucky_draw,
  game_lyric_hunt,
  game_music_trivia,
  game_predict_win,
  game_scratch_card,
  game_spin_wheel,
  live_reporting,
  live_trivia,
  mobile_hero,
  promo_community_radio,
  promo_trivia_rewards,
  promo_try_chat,
  route_based_ads,
  sponsored_games,
};

export default LANDING_IMAGES;
