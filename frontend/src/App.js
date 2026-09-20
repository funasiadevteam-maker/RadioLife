import "@/App.css";
import "@/auth.css";
import { BrowserRouter, Routes, Route, useLocation, useSearchParams, Navigate } from "react-router-dom";
import Radio from "@/Radio";
// Phase 42-A2 — Unified Radio (replaces /live-radio nav entry).
import RadioDiscover from "@/RadioDiscover";
import RadioBrowse from "@/RadioBrowse";
import RadioHome from "@/RadioHome";
import ListenHub from "@/pages/ListenHub";
import DiningHome from "@/pages/dining/DiningHome";
import DiningPlay from "@/pages/dining/DiningPlay";
import DiningPass from "@/pages/dining/DiningPass";
import DiningMerchant from "@/pages/dining/DiningMerchant";
import Admin from "@/Admin";
import AdminHome from "@/pages/admin/AdminHome";  // Phase T — Admin Home dashboard
import AdminAppearance from "@/Admin/AdminAppearance";  // admin-only design switch
import AdminSoftLaunch from "@/Admin/AdminSoftLaunch";  // V2 soft-launch admin
import SocialV2 from "@/pages/social/SocialV2";  // Social V2 — Phase 1
import ListenRoom from "@/pages/social/ListenRoom";  // Listen Together room
import DreamsGuidance from "@/pages/social/DreamsGuidance";  // Dreams & Guidance
import DreamMatchCard from "@/pages/social/DreamMatchCard";  // Public match card
import AdminGlobalSearch from "@/components/AdminGlobalSearch";  // Phase T — Cmd/Ctrl+K palette
import AdminBulkUpload from "@/AdminBulkUpload";  // Phase 22a — bulk music upload
import AdminVoices from "@/AdminVoices";
import PersonaLibrary from "@/PersonaLibrary";
import AdminPersonaSafety from "@/AdminPersonaSafety";
import PrivacyCenter from "@/PrivacyCenter";
import PlacesAndRoutes from "@/PlacesAndRoutes";
import PlaceDetail from "@/PlaceDetail";
import AIMemory from "@/AIMemory";
import GeoInsights from "@/advertiser/GeoInsights";
import News from "@/News";
import NewsDetail from "@/NewsDetail";
import NewsRadio from "@/NewsRadio";
import NewsPreferences from "@/NewsPreferences";
// Phase R — News Radio Expansion (admin-curated news layer).
import NewsPhaseR from "@/pages/News";
import NewsChannelDetail from "@/pages/NewsChannelDetail";
import AdminNews from "@/pages/admin/AdminNews";
// Phase S — Location Intelligence (admin analytics + merchant insights).
import AdminLocationIntel from "@/pages/admin/AdminLocationIntel";
import MerchantInsights from "@/pages/merchant/MerchantInsights";
import Community from "@/Community";
import CreateMyRadio from "@/CreateMyRadio";
import StationPage from "@/pages/StationPage";
// Phase 41 S4.A — In-Store Business TV Display (public kiosk).
import StationTV from "@/pages/StationTV";
import AdminModerationQueue from "@/AdminModerationQueue";
import Feed from "@/Feed";
import { BuyBannerSlot, MyBannerCampaigns } from "@/advertiser/BuyBannerSlot";
import AdminRjQuality from "@/AdminRjQuality";
import AdminImaging from "@/AdminImaging";
import AdminImagingAssets from "@/AdminImagingAssets";
// Phase SC.1 — Stripe Connect merchant status dashboard.
import AdminStripeConnect from "@/AdminStripeConnect";
// Phase SC.2 — Merchant self-service onboarding + admin approval.
import AdminMerchants from "@/AdminMerchants";
import MerchantApply from "@/pages/merchant/MerchantApply";
import MerchantStatus from "@/pages/merchant/MerchantStatus";
import MerchantOnboardingComplete from "@/pages/merchant/MerchantOnboardingComplete";
// Phase SC.3 — Commission Rules Engine + public schedule + merchant dashboard stub.
import AdminCommissions from "@/AdminCommissions";
import AdminTaxRules from "@/AdminTaxRules";
import AdminMarketplacePhaseA from "@/pages/admin/AdminMarketplacePhaseA";  // Super Marketplace Phase A
import LegalCommissions from "@/pages/legal/LegalCommissions";
import MerchantDashboardStub from "@/pages/merchant/MerchantDashboardStub"; // eslint-disable-line no-unused-vars -- kept for reference; MER.1 replaces with MerchantOverview via nested shell route
// Phase SC.4 — Merchant Payment Links portal + public pay page.
import MerchantPaymentLinks from "@/pages/merchant/MerchantPaymentLinks";
import PayPage from "@/pages/pay/PayPage";
// Phase SC.5 — Consumer pay-receipt page (post-payment success/processing).
import PayReceipt from "@/pages/pay/PayReceipt";
// Phase SC.6 — Refunds + Payouts + Disputes admin console + merchant Payouts.
import AdminRefunds from "@/AdminRefunds";
import AdminPayouts from "@/AdminPayouts";
import AdminDisputes from "@/AdminDisputes";
import MerchantPayouts from "@/pages/merchant/MerchantPayouts";
// Phase MER.1 — Merchant desktop portal shell + new pages.
import MerchantShell from "@/pages/merchant/MerchantShell";
import MerchantOverview from "@/pages/merchant/MerchantOverview";
import MerchantTransactions from "@/pages/merchant/MerchantTransactions";
import MerchantProfile from "@/pages/merchant/MerchantProfile";
import MerchantStripe from "@/pages/merchant/MerchantStripe";
import MerchantSettings from "@/pages/merchant/MerchantSettings";
// Phase MER.2 — Staff RBAC + invite + cashier redemption pages.
import MerchantStaff from "@/pages/merchant/MerchantStaff";
import MerchantCashier from "@/pages/merchant/MerchantCashier";
import StaffInvite from "@/pages/StaffInvite";
// Phase MER.3 — Wallet expansion (gift cards + prepaid meals) + wallet v2.
import MerchantGiftCards from "@/pages/merchant/MerchantGiftCards";
import MerchantPrepaidMeals from "@/pages/merchant/MerchantPrepaidMeals";
import WalletV2 from "@/pages/WalletV2";
// Phase MER.4 — Shoppable business profile + follow/save lists.
import BusinessProfile from "@/pages/BusinessProfile";
import MeFollowing from "@/pages/MeFollowing";
import MeSaved from "@/pages/MeSaved";
// Phase PG.1 — Play & Win game engine.
import MerchantGames from "@/pages/merchant/MerchantGames";
import GamePlay from "@/pages/play/GamePlay";
import PlayDiscover from "@/pages/play/PlayDiscover";

// Phase AD.1 — Advertiser self-service dashboard MVP (parallel to Phase 18a).
import AdvertiserApply from "@/pages/advertiser_v2/AdvertiserApply";
import AdvertiserShell from "@/pages/advertiser_v2/AdvertiserShell";
import DeveloperApi from "@/pages/advertiser_v2/DeveloperApi";
import PartnerCheckout from "@/pages/advertiser_v2/PartnerCheckout";
import AdvertiserOverview from "@/pages/advertiser_v2/AdvertiserOverview";
import AdvertiserCampaigns from "@/pages/advertiser_v2/AdvertiserCampaigns";
import AdvertiserBudget from "@/pages/advertiser_v2/AdvertiserBudget";
import AdvertiserSponsoredGames from "@/pages/advertiser_v2/AdvertiserSponsoredGames";
import AdvertiserStaff from "@/pages/advertiser_v2/AdvertiserStaff";
import AdvertiserScan from "@/pages/advertiser_v2/AdvertiserScan";
import AdvertiserStaffAccept from "@/pages/advertiser_v2/AdvertiserStaffAccept";
import AdvertiserCouponCampaigns from "@/pages/advertiser_v2/AdvertiserCouponCampaigns";
// Phase AD.11 — Banner Ad Buying wizard + list.
import AdvertiserBannerCampaigns from "@/pages/advertiser_v2/AdvertiserBannerCampaigns";
// Phase AD.12a — Notification-ad wizard + list.
import AdvertiserNotificationCampaigns from "@/pages/advertiser_v2/AdvertiserNotificationCampaigns";
// Phase AD.3 — Predict & Win sponsorships wizard + list.
import AdvertiserPredictWinSponsorships from "@/pages/advertiser_v2/AdvertiserPredictWinSponsorships";
import AdvertiserFlagshipBoosts from "@/pages/advertiser_v2/AdvertiserFlagshipBoosts";
import AdvertiserPodcastCompletion from "@/pages/advertiser_v2/AdvertiserPodcastCompletion";
// Phase H — AD.5 Trivia sponsorship advertiser dashboard + admin approval queue.
import AdvertiserTriviaSponsorships from "@/pages/advertiser_v2/AdvertiserTriviaSponsorships";
// Phase I — M1 Sponsored AI-RJ Reads advertiser dashboard + admin queue.
import AdvertiserRJSponsoredReads from "@/pages/advertiser_v2/AdvertiserRJSponsoredReads";
// Phase J — M2 Location-Boost Ads advertiser dashboard + admin queue.
import AdvertiserLocationBoosts from "@/pages/advertiser_v2/AdvertiserLocationBoosts";
// Phase K — M3 Marketplace listener + advertiser + admin.
import MarketplacePage from "@/pages/Marketplace";
import AdvertiserMarketplaceSlots from "@/pages/advertiser_v2/AdvertiserMarketplaceSlots";
import AdminFlagshipBoosts from "@/pages/admin/AdminFlagshipBoosts";
import AdminPodcastCompletion from "@/pages/admin/AdminPodcastCompletion";
import AdminTriviaSponsorships from "@/pages/admin/AdminTriviaSponsorships";
import AdminRJSponsoredReads from "@/pages/admin/AdminRJSponsoredReads";
import AdminLocationBoosts from "@/pages/admin/AdminLocationBoosts";
import AdminMarketplaceSlots from "@/pages/admin/AdminMarketplaceSlots";
// Phase L — M5 Radio Takeover Hour advertiser + admin.
import AdvertiserTakeoverHours from "@/pages/advertiser_v2/AdvertiserTakeoverHours";
import AdminTakeoverHours from "@/pages/admin/AdminTakeoverHours";
import TakeoverOverlay from "@/components/TakeoverOverlay";
// Phase M — M6 Retargeting Audiences advertiser + admin.
import AdvertiserRetargeting from "@/pages/advertiser_v2/AdvertiserRetargeting";
import AdminRetargeting from "@/pages/admin/AdminRetargeting";
// Phase N — M7 CPA charges (admin audit + refund).
import AdminCouponCharges from "@/pages/admin/AdminCouponCharges";
// Phase AD.3 bundle — Auction transparency insights.
import AdvertiserAuctionInsights from "@/pages/advertiser_v2/AdvertiserAuctionInsights";
// Phase AD.12a — Consumer notifications full-page feed.
import Notifications from "@/pages/Notifications";
// Phase AD.7 — Scan-to-Pay screens.
import ScanEntry from "@/pages/scan/ScanEntry";
import ScanCheckout from "@/pages/scan/ScanCheckout";
import SplitInvite from "@/pages/scan/SplitInvite";
import MySplits from "@/pages/scan/MySplits";
import MerchantScanToPay from "@/pages/merchant/MerchantScanToPay";import CouponOffers from "@/pages/CouponOffers";
import StorePage from "@/pages/StorePage";
import FpkCouponCaps from "@/pages/admin/FpkCouponCaps";
import AdReview from "@/pages/admin/AdReview";
import AdvertiserAnalyticsAD1 from "@/pages/advertiser_v2/AdvertiserAnalytics";
import AdvertiserProfile from "@/pages/advertiser_v2/AdvertiserProfile";
import AdminAdvertisersAD1 from "@/pages/admin/AdminAdvertisersAD1";

// Phase FUN.1 — Flagship (FunAsia) stations admin surface.
import AdminFlagshipStations from "@/pages/admin/AdminFlagshipStations";
import AdminCampaignsQueue from "@/AdminCampaignsQueue";
import AdminRevenueLive from "@/AdminRevenueLive";
import AdminAnalytics from "@/AdminAnalytics";
import AdminRetention from "@/AdminRetention";
import AdminSafety from "@/AdminSafety";
import ReactivationBanner from "@/ReactivationBanner";
import Advertiser from "@/Advertiser";
import AdvertiserCampaignNew from "@/AdvertiserCampaignNew";
import AdvertiserCampaignWizard from "@/advertiser/CampaignWizard";  // …
import MockStripeCheckout from "@/MockStripeCheckout";  // Phase 36e Turn 1
import { ListenerSubscriptions } from "@/ListenerSubscriptions";  // Phase 36e Turn 1Phase 18a new wizard
import AdvertiserAdminQueue from "@/AdvertiserAdminQueue";              // Phase 18a admin queue
import AIAdCreator from "@/advertiser/AIAdCreator";                            // Phase 18b AI creator
import AdvertiserAnalytics from "@/AdvertiserAnalytics";                       // Phase 18b admin analytics
import AuctionLogPanel from "@/components/AuctionLogPanel";              // Phase 18d.1 admin auction log
import CreatorChannelSettings from "@/CreatorChannelSettings";          // Phase 36d Turn 1 canonical channel settings
import CreatorFunnelDashboard from "@/CreatorFunnelDashboard";          // Phase 36e Turn 2 funnel
import {Highlights as MagicHighlights} from "@/MagicClipsTab";          // Phase 36d Turn 1 global feed
import AdvertiserPayouts from "@/AdvertiserPayouts";
import AdminIntegrations from "@/AdminIntegrations";
import Wallet from "@/Wallet";
import EarnPoints from "@/rewards/EarnPoints";
import MerchantOps from "@/admin/MerchantOps";
import RateCard from "@/admin/RateCard";
import PriceParity from "@/admin/PriceParity";
import Promotions from "@/admin/Promotions";
import Premium from "@/premium/Premium";
import Billing from "@/Billing";
import Audition from "@/Audition";
import Login from "@/Login";
// Phase AUTH.PWR (2026-07-31) — password reset flow pages.
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";
import Onboarding from "@/Onboarding";
import Profile from "@/Profile";
import AuthCallback from "@/AuthCallback";
import AppleAuthReturn from "@/AppleAuthReturn";
import ProtectedRoute from "@/ProtectedRoute";
import ShareLanding from "@/ShareLanding";
import Pricing from "@/Pricing";
import BillingSuccess from "@/BillingSuccess";
import Lobbies from "@/Lobbies";
import Lobby from "@/Lobby";
import PlayAndWin from "@/PlayAndWin";
import GamePlayer from "@/GamePlayer";
import AdvertiserGames, { AdvertiserGameWizard } from "@/AdvertiserGames";
import AdminGamesApproval from "@/AdminGamesApproval";
import PredictWinCampaigns from "@/Admin/PredictWinCampaigns";  // Sub-Phase E1
import StationTracksTab from "@/StationTracksTab";  // Phase D — owner tracks workspace
import AdminTrackModeration from "@/AdminTrackModeration";  // Phase D — admin queue
import PredictWin from "@/PredictWin";  // Sub-Phase E2 — consumer predictions
import StationPredictWinTab from "@/StationPredictWinTab";  // Sub-Phase E3 — business builder
import PredictWinKiosk from "@/PredictWinKiosk";  // Sub-Phase E3 — TV kiosk
import PredictWinCheckin from "@/PredictWinCheckin";  // Sub-Phase E3 — QR landing
import PublicLanding from "@/PublicLanding";
import AdvertiserInsights from "@/AdvertiserInsights";
import { AdminGamesAnalytics, AdminGamesInventory } from "@/AdminPhase8c";
import Commute from "@/Commute";
import CommuteMode from "@/pages/CommuteMode";
// Phase R.1 — FUUSIC design variant overlay + stub for unmapped routes.
import FUUSICOverlay from "@/design_radiolife/RadioLifeOverlay";
import ShopInShell from "@/design_radiolife/ShopInShell";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";
import PublicBusiness from "@/PublicBusiness";
import Coupons from "@/Coupons";
import WalletItems from "@/WalletItems";
// Phase 23 UX-Hotfix B2 — admin context sidebar.
import AdminSidebar from "@/components/AdminSidebar";
// Phase 42-A2 — Backward-compat redirect: /live-radio/station/:id → /radio/station/:id
function LiveRadioStationRedirect() {
  const [params] = useSearchParams();
  const path = window.location.pathname.replace(/^\/live-radio\//, "/radio/");
  return <Navigate to={path + (params.toString() ? "?" + params.toString() : "")} replace />;
}

import PartnerDashboard from "@/PartnerDashboard";
// Phase I — Business Redemption Portal pages (login / register /
// dashboard / redeem / campaigns / ads buy).
// Phase PORTAL.0 — unified portal login + role router (design-independent).
import PortalLogin from "@/pages/portal/PortalLogin";
import PortalRouter from "@/pages/portal/PortalRouter";
import BusinessRegister from "@/pages/BusinessRegister";
import BusinessDashboard from "@/pages/BusinessDashboard";
import BusinessRedeem from "@/pages/BusinessRedeem";
import ShopRedeem from "@/pages/ShopRedeem";
import SponsorBoost from "@/pages/SponsorBoost";
import BusinessCampaigns from "@/pages/BusinessCampaigns";
import BusinessAdsBuy from "@/pages/BusinessAdsBuy";
// Phase J.3 — Stripe checkout return pages.
import { CheckoutSuccess, CheckoutCancel } from "@/pages/CheckoutResult";
// Phase Π — Production readiness primitives (re-added after a P0 outage
// where these imports were lost during edit-merge).
import ErrorBoundary from "@/components/ErrorBoundary";
import CookieBanner from "@/components/CookieBanner";
import FeedbackWidget from "@/components/FeedbackWidget";
import { PrivacyPolicy, TermsOfService, CookiePolicy,
                  DmcaPolicy } from "@/pages/LegalPages";
// Phase Π+1 — Admin system health dashboard (traffic-light readiness).
import AdminHealth from "@/pages/AdminHealth";
// Phase Q — QA Dashboard (admin ops console).
import AdminQADashboard from "@/pages/admin/AdminQADashboard";
// Phase 42-A2 — `/radio` renders either the new Discover home OR the
// existing personalized AI player based on whether a `?ch=` /
// `?channel=` query is present.  Keeps Radio.js completely untouched.
function RadioRouteSwitch() {
  const [params] = useSearchParams();
  const ch = params.get("ch") || params.get("channel");
  // Phase RL.2 — /radio now renders the marketing splash + flagship rail
  // + games + browse teaser.  The old discover rails remain reachable at
  // `/radio/discover` for anyone with a bookmark.
  return ch ? <Radio /> : <RadioHome />;
}

// Phase 42-A2 — Station detail page still uses the 42-A LiveRadioStation
// component (it's source-aware and supports imp_/cmn_/ai_ prefixes via
// the unified backend).  Just remounted under `/radio/station/:id`.
import LiveRadioStation from "@/LiveRadioStation";
// Phase 42-C — Station claiming portal (wizard / verify / owner / admin).
import ClaimStationWizard from "@/ClaimStationWizard";
// Phase CLAIM.1b — Claim Radio Hub landing page.
import ClaimRadioHub from "@/ClaimRadioHub";
import ClaimVerify from "@/ClaimVerify";
import OwnerDashboard from "@/OwnerDashboard";
import AdminRadioClaims from "@/Admin/AdminRadioClaims";
// Phase 42-D2 — admin subscriptions & vouchers UI.
import AdminSubscriptions from "@/Admin/AdminSubscriptions";
// Phase F-1 — Points engine admin dashboard.
import AdminPoints from "@/Admin/AdminPoints";
// Phase 42-E1.3 — Predict & Win self-serve admin + advertiser surfaces.
import AdminPredictWinSelfServe from "@/Admin/AdminPredictWinSelfServe";
import AdvertiserPredictWin from "@/Advertiser/AdvertiserPredictWin";
import Passport from "@/Passport";
import PublicPassport from "@/PublicPassport";
import Leaderboards from "@/Leaderboards";
import { AuthProvider } from "@/AuthContext";
import { RewardProvider } from "@/rewards/RewardOverlay";
import BillingBanner from "@/BillingBanner";
import PageFrame from "@/components/PageFrame";
import { useEffect as _useEffect_ } from "react";
import { useState as _useState_ } from "react";
import axios from "axios";
// Phase 15a — responsive shell + dev styleguide.
import AppShell from "@/shell/AppShell";
import AppShellB from "@/shell/AppShellB";
import Styleguide from "@/shell/Styleguide";
import { Toaster as _ShellToaster_ } from "sonner";
// Phase 15b — Home dashboard, Trivia, Search.
import Home from "@/Home";
import HomeB from "@/HomeB";
import AppShellV2 from "@/design_v2/AppShellV2";
import HomeNewLookV2 from "@/design_v2/HomeNewLookV2";
import PublicHomeNewLookV2 from "@/design_v2/PublicHomeNewLookV2";
import AdminSkipRules from "@/pages/admin/AdminSkipRules";
import AdminRadioLanguage from "@/pages/admin/AdminRadioLanguage";
import AdminAdPacing from "@/pages/admin/AdminAdPacing";  // Phase COMPANION.1 — audio-ad pacing panel
import AdminAdRevenueReport from "@/pages/admin/AdminAdRevenueReport";  // Phase COMPANION.1 — Home ad revenue report
import AdminRailAds from "@/pages/admin/AdminRailAds";  // V2 — right-rail banner moderation
import AdminLandingAnalytics from "@/pages/admin/AdminLandingAnalytics";  // V2 — public landing analytics
import AdminLaunchControls from "@/pages/admin/AdminLaunchControls";  // Soft-launch — Business Setup Mode admin
import PreviewEntry from "@/pages/PreviewEntry";  // Soft-launch — protected preview entry (/preview)
import MerchantSoftLaunch from "@/pages/merchant/MerchantSoftLaunch";  // Soft-launch — 6-months-free merchant claim
import { useLaunchStore, useLaunchBlocked } from "@/hooks/useLaunchStatus";  // Soft-launch — launch status
import Trivia from "@/Trivia";
import TriviaPlay from "@/TriviaPlay";
import { TriviaRoomCreate, TriviaJoin, TriviaRoom } from "@/TriviaRoom";
import TVDisplay from "@/TV";
import {
  VenueDashboard, VenueTVs, VenueTrivia, VenueAnnounce,
  VenueRedeem, VenuePlayers, VenueSettings, VenueOnboard,
} from "@/Venue";
import {
  VenueOffersPage, VenueOffers, VenueOfferNew, VenueOfferImport,
  VenueOfferDetail, VenueScanRedeem,
} from "@/VenueOffers";
// Phase 17b — multi-venue chain rollup + payout reports.
import VenueOrgRollup, { VenuePayouts } from "@/VenueOrg";
import Search from "@/Search";
// Phase 15c — public marketing surface.
import { HelmetProvider } from "react-helmet-async";
import Landing from "@/marketing/Landing";
// Phase LAND.v2 (2026-08-02) — alternative positioning landing page.
import LandingV2 from "@/pages/landing/LandingV2";
import About from "@/marketing/About";
import ForBusiness from "@/marketing/ForBusiness";
import ForAdvertisers from "@/marketing/ForAdvertisers";
import MarketingPricing from "@/marketing/Pricing";
import { LegalTerms, LegalPrivacy } from "@/marketing/Legal";
import Podcasts from "@/Podcasts";
import Creator from "@/Creator";
import AdminPodcasts from "@/AdminPodcasts";
// Phase 19a Part 5 — admin user management surfaces.
import AdminUsers from "@/AdminUsers";
import AdminUserDetail from "@/AdminUserDetail";
import AdminUsersAuditLog from "@/AdminUsersAuditLog";
import TranscriptEditor from "@/TranscriptEditor";
import Studio, { StudioNew } from "@/Studio";
import GuestJoin from "@/GuestJoin";
import { useAuth as _useAuth_ } from "@/AuthContext";
// Phase 15d.3 — hoisted global <audio> mount so radio survives route changes.
import GlobalAudio from "@/components/GlobalAudio";
// Phase 42-A2 — imported live-radio stream bridge (3rd <audio> in the
// player chain, drives `usePlayerStore.importedStation`).
import ImportedStreamBridge from "@/components/ImportedStreamBridge";
// Phase RELIABILITY.P2 — dead-stream user-facing modal.  Listens for
// the `bigfm:station-offline` CustomEvent dispatched by
// ImportedStreamBridge after a double <audio> onError.
import StationOfflineModal from "@/components/StationOfflineModal";
// Phase B — podcast episode playback bridge (4th <audio> in the chain,
// drives `usePlayerStore.podcastEpisode`).
import PodcastPlayerBridge from "@/components/PodcastPlayerBridge";
// Phase B — listener catalog + detail pages.
import PodcastDetail from "@/pages/PodcastDetail";
import CreatorPodcasts from "@/pages/CreatorPodcasts";
// Phase D — Admin RJ Personas management.
import AdminRJPersonas from "@/pages/admin/AdminRJPersonas";

// Phase 10a — capture `?ref=BFM-XXXX` only when landing on the documented
// public landing routes: /play/:slug (games), /business/:slug (commerce),
// /passport/:user_id (10b public profile).  We deliberately do NOT fire
// on /, /wallet, or other authenticated surfaces because a paste of
// `?ref=X` there would be self-attribution noise.
const PUBLIC_LANDING_ROUTE_PREFIXES = ["/play/", "/business/", "/passport/"];

function ReferralCapture() {
  _useEffect_(() => {
    try {
      const u = new URL(window.location.href);
      const rc = u.searchParams.get("ref");
      if (!rc) return;
      const path = u.pathname || "/";
      const matched = PUBLIC_LANDING_ROUTE_PREFIXES.some(p => path.startsWith(p));
      if (!matched) return;
      // Don't re-fire if we already have a cookie for the same code
      const ck = document.cookie.split("; ").find(c => c.startsWith("bigfm_ref="));
      if (ck && ck.includes(rc)) return;
      axios.post(
        `${process.env.REACT_APP_BACKEND_URL}/api/referrals/landing`,
        { ref_code: rc, landing_path: path },
        { withCredentials: true }
      ).catch(() => {});
    } catch (_) {}
  }, []);
  return null;
}

// Toasts sit bottom-right on desktop, but on mobile that corner collides
// with the V2 bottom tab bar (toast portal is above z-40 and eats taps),
// so on <lg widths we render toasts at the top instead.
function _ResponsiveToaster_() {
  const [mobile, setMobile] = _useState_(
    typeof window !== "undefined" ? window.innerWidth < 1024 : false);
  _useEffect_(() => {
    const onR = () => setMobile(window.innerWidth < 1024);
    window.addEventListener("resize", onR);
    return () => window.removeEventListener("resize", onR);
  }, []);
  return (
    <_ShellToaster_
      theme="dark"
      richColors
      position={mobile ? "top-center" : "bottom-right"}
    />
  );
}

function AppRouter() {
  const location = useLocation();
  const designVariant = useDesignVariantStore((s) => s.variant);
  const setVariant = useDesignVariantStore((s) => s.setVariant);
  const { user } = _useAuth_();
  // Lock every customer to New Look V2 — only admins may switch looks
  // (for QA). This overrides any stale variant left in localStorage.
  _useEffect_(() => {
    if ((!user || user.role !== "admin") && designVariant !== "new_look_v2") {
      setVariant("new_look_v2");
    }
  }, [user, designVariant, setVariant]);
  // Soft-launch (Business Setup Mode) — fetch launch status; re-fetch on auth
  // change since bypass depends on the signed-in user.
  _useEffect_(() => { useLaunchStore.getState().fetch(); }, [user]);
  _useEffect_(() => {
    try {
      const t = localStorage.getItem("rl_preview_token");
      if (t) axios.defaults.headers.common["X-Preview-Token"] = t;
    } catch (_e) { /* ignore */ }
  }, []);
  const Shell = designVariant === "new_look_v2" ? AppShellV2
    : designVariant === "classic_b" ? AppShellB : AppShell;
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <>
      <_ResponsiveToaster_ />
      <BillingBanner />
      <ReferralCapture />
      {/* Phase 42 S2 — TOI-style 3-column frame wraps the AppShell.
            Top billboard + sticky left/right skyscrapers + content column
            + mobile sticky bottom. Routes can opt out (login, admin,
            advertiser, etc.) via the EXCLUDE list in PageFrame. */}
      <GlobalAudio />
      <ImportedStreamBridge />
      <StationOfflineModal />
      <PodcastPlayerBridge />
      <TakeoverOverlay />
      <AdminSidebar />
      <AdminGlobalSearch />
      <PageFrame>
      <Shell>
      <LaunchModeGate>
      <Routes>
      <Route path="/" element={<RootGate />} />
      {/* Phase LAND.v2 — alternative positioning landing (public,
              noindexed, does not replace `/`). */}
      <Route path="/l/v2" element={<LandingV2 />} />
      <Route path="/radio" element={<RadioRouteSwitch />} />
      <Route path="/listen" element={
        <ProtectedRoute><ListenHub /></ProtectedRoute>
      } />
      {/* Premium Dining Club (Phase 2/3) */}
      <Route path="/dining" element={<ProtectedRoute><DiningHome /></ProtectedRoute>} />
      <Route path="/dining/enrolled" element={<ProtectedRoute><DiningHome /></ProtectedRoute>} />
      <Route path="/dining/play" element={<ProtectedRoute><DiningPlay /></ProtectedRoute>} />
      <Route path="/dining/pass" element={<ProtectedRoute><DiningPass /></ProtectedRoute>} />
      <Route path="/dining/pass/:orderId" element={<ProtectedRoute><DiningPass /></ProtectedRoute>} />
      <Route path="/dining/merchant" element={<ProtectedRoute><DiningMerchant /></ProtectedRoute>} />
      <Route path="/radio/discover" element={<RadioDiscover />} />
      <Route path="/personas" element={<PersonaLibrary />} />
      <Route path="/privacy" element={<PrivacyCenter />} />
      <Route path="/places" element={
        <ProtectedRoute><PlacesAndRoutes /></ProtectedRoute>
      } />
      <Route path="/places/:place_id" element={
        <ProtectedRoute><PlaceDetail /></ProtectedRoute>
      } />
      <Route path="/me/ai-memory" element={
        <ProtectedRoute><AIMemory /></ProtectedRoute>
      } />
      <Route path="/advertiser/geo-insights" element={
        <ProtectedRoute><GeoInsights /></ProtectedRoute>
      } />
      <Route path="/news" element={
        <ProtectedRoute><News /></ProtectedRoute>
      } />
      {/* Phase R — News Radio Expansion (curator-driven layer). */}
      <Route path="/news/live" element={
        <ProtectedRoute><NewsPhaseR /></ProtectedRoute>
      } />
      <Route path="/news/channels/:channel_id" element={
        <ProtectedRoute><NewsChannelDetail /></ProtectedRoute>
      } />
      <Route path="/news/:news_id" element={
        <ProtectedRoute><NewsDetail /></ProtectedRoute>
      } />
      <Route path="/radio/news" element={<NewsRadio />} />
      <Route path="/news/preferences" element={
        <ProtectedRoute><NewsPreferences /></ProtectedRoute>
      } />
      <Route path="/community" element={
        <ProtectedRoute><Community /></ProtectedRoute>
      } />
      {/* Phase 42-A2 — Unified Radio surface (replaces /live-radio). */}
      <Route path="/radio/browse" element={<RadioBrowse />} />
      <Route path="/radio/station/:id" element={<LiveRadioStation />} />
      {/* Phase 42-C — Station claiming portal. */}
      <Route path="/claim/station/:station_id" element={<ClaimStationWizard />} />
      {/* Phase CLAIM.1b — Claim Radio Hub. */}
      <Route path="/claim-radio" element={<ClaimRadioHub />} />
      <Route path="/claim/verify/:verification_token" element={<ClaimVerify />} />
      <Route path="/owner/dashboard" element={
        <ProtectedRoute><OwnerDashboard /></ProtectedRoute>
      } />
      <Route path="/admin/radio/claims" element={
        <ProtectedRoute requireAdmin><AdminRadioClaims /></ProtectedRoute>
      } />
      {/* Phase 42-D2 — admin Subscriptions & Vouchers */}
      <Route path="/admin/subscriptions" element={
        <ProtectedRoute requireAdmin><AdminSubscriptions /></ProtectedRoute>
      } />
      <Route path="/admin/points" element={
        <ProtectedRoute requireAdmin><AdminPoints /></ProtectedRoute>
      } />
      <Route path="/admin/merchant-ops" element={
        <ProtectedRoute requireAdmin><MerchantOps /></ProtectedRoute>
      } />
      <Route path="/admin/rate-card" element={
        <ProtectedRoute requireAdmin><RateCard /></ProtectedRoute>
      } />
      <Route path="/admin/price-parity" element={
        <ProtectedRoute requireAdmin><PriceParity /></ProtectedRoute>
      } />
      <Route path="/admin/promotions" element={
        <ProtectedRoute requireAdmin><Promotions /></ProtectedRoute>
      } />
      <Route path="/admin/ad-pacing" element={
        <ProtectedRoute requireAdmin><AdminAdPacing /></ProtectedRoute>
      } />
      <Route path="/admin/ad-revenue" element={
        <ProtectedRoute requireAdmin><AdminAdRevenueReport /></ProtectedRoute>
      } />
      <Route path="/admin/rail-ads" element={
        <ProtectedRoute requireAdmin><AdminRailAds /></ProtectedRoute>
      } />
      <Route path="/admin/landing-analytics" element={
        <ProtectedRoute requireAdmin><AdminLandingAnalytics /></ProtectedRoute>
      } />
      <Route path="/admin/predict-win/self-serve" element={
        <ProtectedRoute requireAdmin><AdminPredictWinSelfServe /></ProtectedRoute>
      } />
      <Route path="/advertiser/predict-win" element={
        <ProtectedRoute><AdvertiserPredictWin /></ProtectedRoute>
      } />
      {/* Backward-compat redirects from the Phase 42-A `/live-radio` URLs. */}
      <Route path="/live-radio" element={<Navigate to="/radio" replace />} />
      <Route path="/live-radio/browse" element={<Navigate to="/radio/browse" replace />} />
      <Route path="/live-radio/station/:id" element={<LiveRadioStationRedirect />} />
      <Route path="/radio/create" element={
        <ProtectedRoute><CreateMyRadio /></ProtectedRoute>
      } />
      <Route path="/r/:slug" element={
        <ProtectedRoute><StationPage /></ProtectedRoute>
      } />
      {/* Phase 41 S4.A — In-Store Business TV Display (UNAUTH kiosk).
          Lives OUTSIDE ProtectedRoute so screens at a physical
          location don't need to log in. */}
      <Route path="/tv/:slug" element={<StationTV />} />
      <Route path="/admin/moderation" element={
        <ProtectedRoute><AdminModerationQueue /></ProtectedRoute>
      } />
      <Route path="/feed" element={
        <ProtectedRoute><Feed /></ProtectedRoute>
      } />
      <Route path="/advertiser/banner/buy" element={
        <ProtectedRoute><BuyBannerSlot /></ProtectedRoute>
      } />
      <Route path="/advertiser/banner/campaigns" element={
        <ProtectedRoute><MyBannerCampaigns /></ProtectedRoute>
      } />
      <Route path="/admin/personas/safety" element={
        <ProtectedRoute requireAdmin><AdminPersonaSafety /></ProtectedRoute>
      } />
      <Route path="/trivia" element={<Trivia />} />
      <Route path="/trivia/play" element={<TriviaPlay />} />
      <Route path="/trivia/rooms/create" element={
        <ProtectedRoute><TriviaRoomCreate /></ProtectedRoute>
      } />
      <Route path="/trivia/join" element={
        <ProtectedRoute><TriviaJoin /></ProtectedRoute>
      } />
      <Route path="/trivia/rooms/:code" element={
        <ProtectedRoute><TriviaRoom /></ProtectedRoute>
      } />
      {/* Phase 16c — TV display (token-paired, no user auth needed) */}
      <Route path="/tv" element={<TVDisplay />} />
      {/* Phase 16c — Venue Staff dashboard */}
      <Route path="/venue/onboard" element={
        <ProtectedRoute><VenueOnboard /></ProtectedRoute>
      } />
      <Route path="/venue" element={
        <ProtectedRoute><VenueDashboard /></ProtectedRoute>
      } />
      <Route path="/venue/tvs" element={
        <ProtectedRoute><VenueTVs /></ProtectedRoute>
      } />
      <Route path="/venue/trivia" element={
        <ProtectedRoute><VenueTrivia /></ProtectedRoute>
      } />
      <Route path="/venue/announcements" element={
        <ProtectedRoute><VenueAnnounce /></ProtectedRoute>
      } />
      <Route path="/venue/redeem" element={
        <ProtectedRoute><VenueRedeem /></ProtectedRoute>
      } />
      <Route path="/venue/players" element={
        <ProtectedRoute><VenuePlayers /></ProtectedRoute>
      } />
      <Route path="/venue/settings" element={
        <ProtectedRoute><VenueSettings /></ProtectedRoute>
      } />
      {/* Phase 17a — Offer CRUD, bulk import, QR scanner */}
      <Route path="/venue/offers" element={
        <ProtectedRoute><VenueOffersPage Component={VenueOffers} title="Offers" /></ProtectedRoute>
      } />
      <Route path="/venue/offers/new" element={
        <ProtectedRoute><VenueOffersPage Component={VenueOfferNew} title="New offer" /></ProtectedRoute>
      } />
      <Route path="/venue/offers/import" element={
        <ProtectedRoute><VenueOffersPage Component={VenueOfferImport} title="Import offers" /></ProtectedRoute>
      } />
      <Route path="/venue/offers/:offerId" element={
        <ProtectedRoute><VenueOffersPage Component={VenueOfferDetail} title="Offer detail" /></ProtectedRoute>
      } />
      <Route path="/venue/redeem/scan" element={
        <ProtectedRoute><VenueOffersPage Component={VenueScanRedeem} title="QR scan" /></ProtectedRoute>
      } />
      {/* Phase 17b — Multi-venue org rollup + per-venue payouts */}
      <Route path="/venue/orgs/:orgId" element={
        <ProtectedRoute><VenueOrgRollup /></ProtectedRoute>
      } />
      <Route path="/venue/:venueId/payouts" element={
        <ProtectedRoute><VenuePayouts /></ProtectedRoute>
      } />
      <Route path="/search" element={<Search />} />
      {/* Phase 15c — public marketing surface. AppShell skips these via
                MARKETING_ROUTES regex; each page mounts its own MarketingShell. */}
      <Route path="/about" element={<About />} />
      <Route path="/for-business" element={<ForBusiness />} />
      <Route path="/for-advertisers" element={<ForAdvertisers />} />
      <Route path="/legal/terms" element={<LegalTerms />} />
      <Route path="/podcasts" element={<Podcasts />} />
      {/* Phase B — podcast listener detail page + creator podcasts alias. */}
      <Route path="/podcasts/:podcast_id" element={<PodcastDetail />} />
      <Route path="/creator/podcasts" element={<CreatorPodcasts />} />
      <Route path="/creator" element={<Creator />} />
      <Route path="/creator/episodes/:ep_id/edit" element={<TranscriptEditor />} />
      <Route path="/creator/studio/new" element={<StudioNew />} />
      <Route path="/creator/studio/:sid" element={<Studio />} />
      <Route path="/studio/join/:token" element={<GuestJoin />} />
      {/* Phase 36e Turn 1 — mock Stripe checkout + listener subs surfaces */}
      <Route path="/mock/stripe/checkout" element={<MockStripeCheckout />} />
      <Route path="/listener/subscriptions" element={
        <ProtectedRoute><ListenerSubscriptions /></ProtectedRoute>
      } />
      {/* Phase 19a — close open-route gap: admin podcast routes were not gated. */}
      <Route path="/admin/podcasts/applications" element={
        <ProtectedRoute requireAdmin><AdminPodcasts /></ProtectedRoute>
      } />
      <Route path="/admin/podcasts/channels" element={
        <ProtectedRoute requireAdmin><AdminPodcasts /></ProtectedRoute>
      } />
      {/* Phase 19a Part 5 — admin user management. */}
      <Route path="/admin/users" element={
        <ProtectedRoute requireAdmin><AdminUsers /></ProtectedRoute>
      } />
      <Route path="/admin/users/audit-log" element={
        <ProtectedRoute requireAdmin><AdminUsersAuditLog /></ProtectedRoute>
      } />
      <Route path="/admin/users/:user_id" element={
        <ProtectedRoute requireAdmin><AdminUserDetail /></ProtectedRoute>
      } />
      <Route path="/legal/privacy" element={<LegalPrivacy />} />
      <Route path="/login" element={<Login />} />
      {/* Phase AUTH.PWR — password recovery. */}
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/auth/apple/return" element={<AppleAuthReturn />} />
      <Route path="/onboarding" element={
        <ProtectedRoute allowUnonboarded><Onboarding /></ProtectedRoute>
      } />
      <Route path="/profile" element={
        <ProtectedRoute><Profile /></ProtectedRoute>
      } />
      {/* Phase T — Admin Home dashboard replaces legacy stub. */}
      <Route path="/admin" element={
        <ProtectedRoute requireAdmin><AdminHome /></ProtectedRoute>
      } />
      <Route path="/admin/appearance" element={
        <ProtectedRoute requireAdmin><AdminAppearance /></ProtectedRoute>
      } />
      <Route path="/admin/soft-launch" element={
        <ProtectedRoute requireAdmin><AdminSoftLaunch /></ProtectedRoute>
      } />
      <Route path="/admin/legacy" element={
        <ProtectedRoute requireAdmin><Admin /></ProtectedRoute>
      } />
      <Route path="/admin/bulk-upload" element={
        <ProtectedRoute requireAdmin><AdminBulkUpload /></ProtectedRoute>
      } />
      <Route path="/admin/voices" element={
        <ProtectedRoute requireAdmin><AdminVoices /></ProtectedRoute>
      } />
      <Route path="/admin/rj-quality" element={
        <ProtectedRoute requireAdmin><AdminRjQuality /></ProtectedRoute>
      } />
      {/* Phase D — AI RJ Personas admin */}
      <Route path="/admin/rj-personas" element={
        <ProtectedRoute requireAdmin><AdminRJPersonas /></ProtectedRoute>
      } />
      <Route path="/admin/imaging" element={
        <ProtectedRoute requireAdmin><AdminImaging /></ProtectedRoute>
      } />
      <Route path="/admin/radio-settings" element={
        <ProtectedRoute requireAdmin><AdminSkipRules /></ProtectedRoute>
      } />
      <Route path="/admin/radio-language" element={
        <ProtectedRoute requireAdmin><AdminRadioLanguage /></ProtectedRoute>
      } />
      <Route path="/admin/imaging/:station/assets" element={
        <ProtectedRoute requireAdmin><AdminImagingAssets /></ProtectedRoute>
      } />
      <Route path="/admin/campaigns/queue" element={
        <ProtectedRoute requireAdmin><AdminCampaignsQueue /></ProtectedRoute>
      } />
      <Route path="/admin/ads/revenue" element={
        <ProtectedRoute requireAdmin><AdminRevenueLive /></ProtectedRoute>
      } />
      <Route path="/admin/ads/auction-log" element={
        <ProtectedRoute requireAdmin><AuctionLogPanel /></ProtectedRoute>
      } />
      <Route path="/creator/channels/:channel_id/settings" element={
        <ProtectedRoute><CreatorChannelSettings /></ProtectedRoute>
      } />
      <Route path="/creator/funnel" element={
        <ProtectedRoute><CreatorFunnelDashboard /></ProtectedRoute>
      } />
      <Route path="/creator/funnel/:creator_id" element={
        <ProtectedRoute><CreatorFunnelDashboard /></ProtectedRoute>
      } />
      <Route path="/highlights" element={<MagicHighlights />} />
      <Route path="/admin/revenue/live" element={
        <ProtectedRoute requireAdmin><AdminRevenueLive /></ProtectedRoute>
      } />
      <Route path="/admin/analytics" element={
        <ProtectedRoute requireAdmin><AdminAnalytics /></ProtectedRoute>
      } />
      {/* Phase SC.1 — Stripe Connect merchant status dashboard (admin-only). */}
      <Route path="/admin/stripe-connect" element={
        <ProtectedRoute requireAdmin><AdminStripeConnect /></ProtectedRoute>
      } />
      {/* Phase SC.2 — Merchants (admin) supersedes the SC.1 label; the
              legacy /admin/stripe-connect route is kept as a working alias. */}
      <Route path="/admin/merchants" element={
        <ProtectedRoute requireAdmin><AdminMerchants /></ProtectedRoute>
      } />
      {/* Phase SC.2 — Merchant self-service wizard + status pages. */}
      <Route path="/merchant/apply" element={<MerchantApply />} />
      <Route path="/merchant/status" element={<MerchantStatus />} />
      <Route path="/merchant/onboarding/complete" element={<MerchantOnboardingComplete />} />
      <Route path="/merchant/onboarding/refresh" element={<MerchantOnboardingComplete />} />
      {/* Phase SC.3 — Commissions admin + public schedule + merchant dashboard stub. */}
      <Route path="/admin/commissions" element={
        <ProtectedRoute requireAdmin><AdminCommissions /></ProtectedRoute>
      } />
      <Route path="/admin/tax" element={
        <ProtectedRoute requireAdmin><AdminTaxRules /></ProtectedRoute>
      } />
      <Route path="/admin/marketplace" element={
        <ProtectedRoute requireAdmin><AdminMarketplacePhaseA /></ProtectedRoute>
      } />
      <Route path="/legal/commissions" element={<LegalCommissions />} />
      {/* Phase MER.1 — Merchant portal shell + nested pages.
                Wraps existing SC.4 payment-links + SC.6 payouts in the unified
                shell layout without modifying their internal logic. */}
      <Route path="/merchant" element={<MerchantShell />}>
        <Route path="dashboard"          element={<MerchantOverview />} />
        <Route path="payment-links"  element={<MerchantPaymentLinks />} />
        <Route path="transactions"    element={<MerchantTransactions />} />
        <Route path="payouts"              element={<MerchantPayouts />} />
        <Route path="staff"                  element={<MerchantStaff />} />
        <Route path="cashier"              element={<MerchantCashier />} />
        <Route path="gift-cards"        element={<MerchantGiftCards />} />
        <Route path="prepaid-meals"  element={<MerchantPrepaidMeals />} />
        <Route path="games"                element={<MerchantGames />} />
        <Route path="profile"              element={<MerchantProfile />} />
        <Route path="stripe"                element={<MerchantStripe />} />
        <Route path="settings"            element={<MerchantSettings />} />
        {/* Phase S — foot-traffic insights. */}
        <Route path="insights"              element={<MerchantInsights />} />
      </Route>
      {/* Phase MER.2 — Public staff-invite acceptance page (no MerchantShell). */}
      <Route path="/staff/invite/:token" element={<StaffInvite />} />
      {/* Phase MER.3 — Consumer Wallet v2 (coupons + gift cards + meal packs + points). */}
      <Route path="/wallet-v2" element={<WalletV2 />} />
      {/* Phase AD.12a — Consumer notifications inbox (full-page). */}
      <Route path="/notifications" element={<Notifications />} />
      {/* Phase AD.7 — Scan-to-Pay entry + checkout + merchant terminal. */}
      <Route path="/scan" element={<ScanEntry />} />
      <Route path="/scan-to-pay/:token" element={<ScanCheckout />} />
      <Route path="/split/:invite_token" element={<SplitInvite />} />
      <Route path="/my/splits" element={<MySplits />} />
      <Route path="/merchant/:merchantId/scan-to-pay" element={<MerchantScanToPay />} />
      {/* Phase MER.4 — Follow/save lists. Business profile route is registered
                below alongside the other /business/* routes to preserve segment ordering. */}
      <Route path="/me/following" element={<MeFollowing />} />
      <Route path="/me/saved" element={<MeSaved />} />
      {/* Phase PG.1 — Consumer game player + discovery. */}
      <Route path="/play" element={<PlayDiscover />} />
      <Route path="/play/:campaign_id" element={<GamePlay />} />
      {/* Phase AD.1 — Advertiser self-service (mounted BEFORE the legacy
              /advertiser/* catch-all so the new paths take precedence). */}
      <Route path="/advertiser/apply" element={
        <ProtectedRoute><AdvertiserApply /></ProtectedRoute>
      } />
      {/* Phase AD.6 — advertiser staff invite accept flow.  Public preview,
              authed accept — both handled inside the same page. */}
      <Route path="/advertiser-app/staff/accept/:token" element={<AdvertiserStaffAccept />} />
      {/* Phase AD.4 — customer-facing coupon offers surface. */}
      <Route path="/offers" element={<CouponOffers />} />
      <Route path="/store/:id" element={<StorePage />} />
      <Route path="/admin/fpk-caps" element={
        <ProtectedRoute requireAdmin><FpkCouponCaps /></ProtectedRoute>} />
      {/* Phase ADMOD.1 — Ad Manager · Unified creative approval queue. */}
      <Route path="/admin/ad-review" element={
        <ProtectedRoute><AdReview /></ProtectedRoute>
      } />
      <Route path="/advertiser/dashboard" element={
        <ProtectedRoute><AdvertiserShell /></ProtectedRoute>
      }>
        <Route index element={<AdvertiserOverview />} />
        <Route path="overview" element={<AdvertiserOverview />} />
        <Route path="campaigns" element={<AdvertiserCampaigns />} />
        <Route path="sponsored-games" element={<AdvertiserSponsoredGames />} />
        <Route path="coupon-campaigns" element={<AdvertiserCouponCampaigns />} />
        <Route path="banner-campaigns" element={<AdvertiserBannerCampaigns />} />
        <Route path="notification-campaigns" element={<AdvertiserNotificationCampaigns />} />
        <Route path="predict-win-sponsorships" element={<AdvertiserPredictWinSponsorships />} />
        <Route path="flagship-boosts" element={<AdvertiserFlagshipBoosts />} />
        <Route path="podcast-completion" element={<AdvertiserPodcastCompletion />} />
        <Route path="trivia-sponsorships" element={<AdvertiserTriviaSponsorships />} />
        <Route path="rj-sponsored-reads" element={<AdvertiserRJSponsoredReads />} />
        <Route path="location-boosts" element={<AdvertiserLocationBoosts />} />
        <Route path="marketplace-slots" element={<AdvertiserMarketplaceSlots />} />
        <Route path="takeover-hours" element={<AdvertiserTakeoverHours />} />
        <Route path="retargeting" element={<AdvertiserRetargeting />} />
        <Route path="auction-insights" element={<AdvertiserAuctionInsights />} />
        <Route path="staff" element={<AdvertiserStaff />} />
        <Route path="scan" element={<AdvertiserScan />} />
        <Route path="budget" element={<AdvertiserBudget />} />
        <Route path="analytics" element={<AdvertiserAnalyticsAD1 />} />
        <Route path="profile" element={<AdvertiserProfile />} />
        <Route path="api" element={<DeveloperApi />} />
        <Route path="api-checkout" element={<PartnerCheckout />} />
      </Route>
      <Route path="/admin/advertisers" element={
        <ProtectedRoute requireAdmin><AdminAdvertisersAD1 /></ProtectedRoute>
      } />
      {/* Phase FUN.1 — Admin flagship-stations management. */}
      <Route path="/admin/flagship-stations" element={
        <ProtectedRoute requireAdmin><AdminFlagshipStations /></ProtectedRoute>
      } />
      {/* Phase F — Monetization M4: Boosted Flagship Slots. */}
      <Route path="/admin/flagship-boosts" element={
        <ProtectedRoute requireAdmin><AdminFlagshipBoosts /></ProtectedRoute>
      } />
      {/* Phase G — AD.9 Podcast Completion Points. */}
      <Route path="/admin/podcast-completion" element={
        <ProtectedRoute requireAdmin><AdminPodcastCompletion /></ProtectedRoute>
      } />
      {/* Phase H — AD.5 Trivia Sponsorships (admin approval). */}
      <Route path="/admin/trivia-sponsorships" element={
        <ProtectedRoute requireAdmin><AdminTriviaSponsorships /></ProtectedRoute>
      } />
      {/* Phase I — M1 Sponsored AI-RJ Reads (admin moderation queue). */}
      <Route path="/admin/rj-sponsored-reads" element={
        <ProtectedRoute requireAdmin><AdminRJSponsoredReads /></ProtectedRoute>
      } />
      {/* Phase J — M2 Location-Boost Ads (admin approval queue). */}
      <Route path="/admin/location-boosts" element={
        <ProtectedRoute requireAdmin><AdminLocationBoosts /></ProtectedRoute>
      } />
      {/* Phase K — M3 Marketplace Featured Slots (admin approval queue). */}
      <Route path="/admin/marketplace-slots" element={
        <ProtectedRoute requireAdmin><AdminMarketplaceSlots /></ProtectedRoute>
      } />
      {/* Phase L — M5 Radio Takeover Hours (admin moderation queue). */}
      <Route path="/admin/takeover-hours" element={
        <ProtectedRoute requireAdmin><AdminTakeoverHours /></ProtectedRoute>
      } />
      {/* Phase M — M6 Retargeting Audiences (admin view). */}
      <Route path="/admin/retargeting" element={
        <ProtectedRoute requireAdmin><AdminRetargeting /></ProtectedRoute>
      } />
      {/* Phase N — M7 CPA charges audit. */}
      <Route path="/admin/coupon-charges" element={
        <ProtectedRoute requireAdmin><AdminCouponCharges /></ProtectedRoute>
      } />
      {/* Phase K — M3 Marketplace listener browse (public — auth optional). */}
      <Route path="/marketplace" element={<MarketplacePage />} />
      {/* Phase SC.4 — Public consumer pay page (kept OUTSIDE shell — no auth). */}
      <Route path="/pay/:token" element={<PayPage />} />
      {/* Phase SC.5 — Post-payment receipt page (public, polls until succeeded). */}
      <Route path="/pay/:token/receipt" element={<PayReceipt />} />
      {/* Phase SC.6 — Refunds + Payouts + Disputes admin + merchant Payouts. */}
      <Route path="/admin/refunds" element={
        <ProtectedRoute requireAdmin><AdminRefunds /></ProtectedRoute>
      } />
      <Route path="/admin/payouts" element={
        <ProtectedRoute requireAdmin><AdminPayouts /></ProtectedRoute>
      } />
      <Route path="/admin/disputes" element={
        <ProtectedRoute requireAdmin><AdminDisputes /></ProtectedRoute>
      } />
      <Route path="/admin/retention" element={
        <ProtectedRoute requireAdmin><AdminRetention /></ProtectedRoute>
      } />
      <Route path="/admin/safety" element={
        <ProtectedRoute requireAdmin><AdminSafety /></ProtectedRoute>
      } />
      <Route path="/advertiser" element={
        <ProtectedRoute><Advertiser /></ProtectedRoute>
      } />
      {/* Phase 18a — nested advertiser subroutes (overview, campaigns, etc.) */}
      <Route path="/advertiser/*" element={
        <ProtectedRoute><Advertiser /></ProtectedRoute>
      } />
      <Route path="/advertiser/campaigns/new" element={
        <ProtectedRoute><AdvertiserCampaignWizard /></ProtectedRoute>
      } />
      <Route path="/admin/advertiser/campaigns" element={
        <ProtectedRoute requireAdmin><AdvertiserAdminQueue /></ProtectedRoute>
      } />
      <Route path="/admin/advertiser/analytics" element={
        <ProtectedRoute requireAdmin><AdvertiserAnalytics /></ProtectedRoute>
      } />
      <Route path="/advertiser/creatives/ai" element={
        <ProtectedRoute><AIAdCreator /></ProtectedRoute>
      } />
      <Route path="/advertiser/campaigns/new" element={
        <ProtectedRoute><AdvertiserCampaignNew /></ProtectedRoute>
      } />
      <Route path="/advertiser/payouts" element={
        <ProtectedRoute><AdvertiserPayouts /></ProtectedRoute>
      } />
      <Route path="/admin/integrations" element={
        <ProtectedRoute requireAdmin><AdminIntegrations /></ProtectedRoute>
      } />
      <Route path="/wallet" element={
        <ProtectedRoute><Wallet /></ProtectedRoute>
      } />
      <Route path="/earn" element={
        <ProtectedRoute><EarnPoints /></ProtectedRoute>
      } />
      <Route path="/billing" element={
        <ProtectedRoute><Billing /></ProtectedRoute>
      } />
      <Route path="/pricing" element={<PricingGate />} />
      <Route path="/premium" element={
        <ProtectedRoute><Premium /></ProtectedRoute>
      } />
      <Route path="/billing/success" element={
        <ProtectedRoute><BillingSuccess /></ProtectedRoute>
      } />
      <Route path="/r/:share_id" element={<ShareLanding />} />
      <Route path="/audition" element={<Audition />} />
      <Route path="/lobbies" element={
        <ProtectedRoute><Lobbies /></ProtectedRoute>
      } />
      <Route path="/lobby/:id" element={
        <ProtectedRoute><Lobby /></ProtectedRoute>
      } />
      <Route path="/play-and-win" element={
        <ProtectedRoute><PlayAndWin /></ProtectedRoute>
      } />
      <Route path="/play" element={
        <ProtectedRoute><PlayAndWin /></ProtectedRoute>
      } />
      <Route path="/map" element={
        <ProtectedRoute><Commute /></ProtectedRoute>
      } />
      <Route path="/play-and-win/:campaign_id" element={
        <ProtectedRoute><GamePlayer /></ProtectedRoute>
      } />
      <Route path="/advertiser/games" element={
        <ProtectedRoute><AdvertiserGames /></ProtectedRoute>
      } />
      <Route path="/advertiser/games/new" element={
        <ProtectedRoute><AdvertiserGameWizard /></ProtectedRoute>
      } />
      {/* Phase 23 Session 3 — admin-creator path reuses the wizard. */}
      <Route path="/admin/games/new" element={
        <ProtectedRoute requireAdmin><AdvertiserGameWizard /></ProtectedRoute>
      } />
      <Route path="/admin/games-approval" element={
        <ProtectedRoute requireAdmin><AdminGamesApproval /></ProtectedRoute>
      } />
      {/* Sub-Phase E1 — Predict & Win admin campaigns workspace. */}
      <Route path="/admin/predict-win/campaigns" element={
        <ProtectedRoute requireAdmin><PredictWinCampaigns /></ProtectedRoute>
      } />
      {/* Phase D — User-station tracks workspace (owner-only). */}
      <Route path="/station/:slug/tracks" element={
        <ProtectedRoute><StationTracksTab /></ProtectedRoute>
      } />
      {/* Phase D — Admin track moderation queue. */}
      <Route path="/admin/moderation/tracks" element={
        <ProtectedRoute requireAdmin><AdminTrackModeration /></ProtectedRoute>
      } />
      {/* Sub-Phase E2 — Predict & Win consumer tab. */}
      <Route path="/predict-win" element={<PredictWin />} />
      {/* Sub-Phase E3 — Business builder + venue check-in + TV kiosk. */}
      <Route path="/station/:slug/predict-win" element={
        <ProtectedRoute><StationPredictWinTab /></ProtectedRoute>
      } />
      <Route path="/predict-win/checkin" element={<PredictWinCheckin />} />
      <Route path="/tv/predict-win/:pairing_code" element={<PredictWinKiosk />} />
      <Route path="/play/:slug" element={<PublicLanding />} />
      <Route path="/advertiser/games-insights" element={
        <ProtectedRoute><AdvertiserInsights /></ProtectedRoute>} />
      <Route path="/admin/games-analytics" element={
        <ProtectedRoute requireAdmin><AdminGamesAnalytics /></ProtectedRoute>} />
      <Route path="/admin/games-inventory" element={
        <ProtectedRoute requireAdmin><AdminGamesInventory /></ProtectedRoute>} />
      <Route path="/commute" element={
        <ProtectedRoute><CommuteMode /></ProtectedRoute>} />
      <Route path="/commute/legacy" element={
        <ProtectedRoute><Commute /></ProtectedRoute>} />
      {/* Phase I — Business Redemption Portal.  Static routes appear
            before the dynamic /business/:slug PublicBusiness page so they
            take precedence (react-router v6 ranks static segments higher
            than dynamic ones regardless of order). */}
      {/* Phase PORTAL.0 — Unified portal (design-independent routes).
                /business/login now redirects into the shared /portal/login. */}
      <Route path="/portal/login" element={<PortalLogin />} />
      <Route path="/portal" element={<PortalRouter />} />
      <Route path="/business/login" element={<Navigate to="/portal/login" replace />} />

      {/* Social V2 — Phase 1 (design-independent; premium V2 presentation). */}
      <Route path="/social" element={<ProtectedRoute><SocialV2 /></ProtectedRoute>} />
      <Route path="/social/room/:id" element={<ProtectedRoute><ListenRoom /></ProtectedRoute>} />
      <Route path="/social/dreams" element={<ProtectedRoute><DreamsGuidance /></ProtectedRoute>} />
      <Route path="/dreams/match/:cardId" element={<DreamMatchCard />} />
      <Route path="/business/register" element={
        <ProtectedRoute><BusinessRegister /></ProtectedRoute>} />
      <Route path="/business" element={
        <ProtectedRoute><BusinessDashboard /></ProtectedRoute>} />
      <Route path="/business/redeem" element={
        <ProtectedRoute><BusinessRedeem /></ProtectedRoute>} />
      <Route path="/shop/redeem" element={<ShopRedeem />} />
      <Route path="/promote/boost" element={<SponsorBoost />} />
      <Route path="/business/campaigns" element={
        <ProtectedRoute><BusinessCampaigns /></ProtectedRoute>} />
      <Route path="/business/ads/buy" element={
        <ProtectedRoute><BusinessAdsBuy /></ProtectedRoute>} />
      {/* Phase J.3 — Stripe checkout return pages.  Public — Stripe
            redirects to these by URL only (no auth header). */}
      <Route path="/checkout/success" element={<CheckoutSuccess />} />
      <Route path="/checkout/cancel" element={<CheckoutCancel />} />
      {/* Phase Π.3 — Legal pages (public, indexable). */}
      <Route path="/privacy" element={<PrivacyPolicy />} />
      <Route path="/terms" element={<TermsOfService />} />
      <Route path="/cookies" element={<CookiePolicy />} />
      <Route path="/dmca" element={<DmcaPolicy />} />
      {/* Phase Π+1 — Admin system health dashboard. */}
      <Route path="/admin/health" element={
        <ProtectedRoute><AdminHealth /></ProtectedRoute>} />
      {/* Phase Q — QA Dashboard (admin ops console). */}
      <Route path="/admin/qa" element={
        <ProtectedRoute requireAdmin><AdminQADashboard /></ProtectedRoute>} />
      {/* Phase R — News Radio admin. */}
      <Route path="/admin/news" element={
        <ProtectedRoute requireAdmin><AdminNews /></ProtectedRoute>} />
      {/* Phase S — Location Intelligence admin analytics. */}
      <Route path="/admin/location-intel" element={
        <ProtectedRoute requireAdmin><AdminLocationIntel /></ProtectedRoute>} />
      {/* Phase 9c — Local Commerce */}
      <Route path="/business/:slug" element={<BusinessProfile />} />
      <Route path="/wallet/coupons" element={
        <ProtectedRoute><Coupons /></ProtectedRoute>} />
      {/* Phase 23 Session 9 — new server-resolved wallet_items surface */}
      <Route path="/wallet/items" element={
        <ProtectedRoute><WalletItems /></ProtectedRoute>} />
      <Route path="/partner" element={
        <ProtectedRoute><PartnerDashboard /></ProtectedRoute>} />
      {/* Phase 10a — Social Passport (listener private view) */}
      <Route path="/passport" element={
        <ProtectedRoute><Passport /></ProtectedRoute>} />
      {/* Phase 10b — Public passport profile + leaderboards */}
      <Route path="/passport/:userId" element={<PublicPassport />} />
      <Route path="/leaderboards" element={<Leaderboards />} />
      <Route path="/leaderboards/:city" element={<Leaderboards />} />
      {/* Phase 15a — dev-only styleguide. Excluded from shell chrome
          via BARE_ROUTES regex in shell/AppShell.jsx. */}
      <Route path="/dev/styleguide" element={<Styleguide />} />
      {/* Phase R.1 — FUUSIC-only routes.  In legacy variant these
          render nothing meaningful (FUUSICVariantWrapper intercepts
          them in FUUSIC mode).  We register no-op placeholders so
          the router doesn't 404 on direct-load. */}
      <Route path="/pay" element={
        <ProtectedRoute><ScanEntry /></ProtectedRoute>} />
      <Route path="/discover" element={
        <ProtectedRoute><FUUSICStubPage title="Discover" hint="Enable FUUSIC design to preview Discover." /></ProtectedRoute>} />
      <Route path="/shop" element={
        <ProtectedRoute><ShopInShell /></ProtectedRoute>} />
      <Route path="/shop/*" element={
        <ProtectedRoute><ShopInShell /></ProtectedRoute>} />
      <Route path="/sell" element={
        <ProtectedRoute><ShopInShell /></ProtectedRoute>} />
      <Route path="/coupon/:coupon_id" element={
        <ProtectedRoute><FUUSICStubPage title="Coupon" hint="Enable FUUSIC design to preview Redeem." /></ProtectedRoute>} />
      {/* Soft-launch — Business Setup Mode routes. */}
      <Route path="/preview" element={<PreviewEntry />} />
      <Route path="/merchant/soft-launch" element={<ProtectedRoute><MerchantSoftLaunch /></ProtectedRoute>} />
      <Route path="/admin/launch" element={<ProtectedRoute requireAdmin><AdminLaunchControls /></ProtectedRoute>} />
      </Routes>
      </LaunchModeGate>
      </Shell>
      </PageFrame>
      {/* Phase R.1 — Overlay FUUSIC variant on top of the legacy shell
            when the variant toggle is ON.  The wrapper reads the current
            pathname and renders the FUUSIC screen; when there's no
            FUUSIC screen for a path, it returns null (legacy shows through). */}
      <FUUSICOverlay />
    </>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <HelmetProvider>
        <BrowserRouter>
          <AuthProvider>
            <RewardProvider>
              <AppRouter />
            </RewardProvider>
            {/* Phase Π.3 — GDPR/CCPA consent + footer. */}
            <CookieBanner />
            {/* Phase Π.5 — Feedback fab for employees + admins. */}
            <FeedbackWidget />
          </AuthProvider>
        </BrowserRouter>
      </HelmetProvider>
    </ErrorBoundary>
  );
}

// Phase 15c — `/` is the brand front door. Logged-out visitors see the
// marketing Landing (which mounts its own MarketingShell). Logged-in
// listeners see the Home dashboard (which sits inside DesktopShell).
// AppShell consults useAuth() and treats `/` as bare when anon so the
// listener chrome doesn't wrap the marketing surface.
// Soft-launch — Business Setup Mode gate. When the mode is ON and the visitor
// lacks bypass, consumer routes bounce to "/" (Coming Soon). Open paths (auth,
// business/merchant signup, admin, preview, waitlist, legal) always render.
const LAUNCH_OPEN_PATHS = [
  "/login", "/signup", "/register", "/logout", "/auth", "/onboarding",
  "/business", "/merchant", "/for-business", "/sell",
  "/preview", "/admin", "/waitlist", "/privacy", "/terms",
  "/l/v2", "/pricing", "/payment",
];
function _launchIsOpen(p) {
  if (p === "/") return true;
  return LAUNCH_OPEN_PATHS.some((o) => p === o || p.startsWith(o + "/"));
}
export function LaunchModeGate({ children }) {
  const blocked = useLaunchBlocked();
  const { pathname } = useLocation();
  if (blocked && !_launchIsOpen(pathname)) {
    return <Navigate to="/" replace />;
  }
  return children;
}

export function RootGate() {
  const { user, loading } = _useAuth_();
  const designVariant = useDesignVariantStore((s) => s.variant);
  const blocked = useLaunchBlocked();
  const offerMonths = useLaunchStore((s) => s.offerMonths);
  const waitlistEnabled = useLaunchStore((s) => s.waitlistEnabled);
  const launchAt = useLaunchStore((s) => s.launchAt);
  if (loading) return null;
  if (blocked) {
    // Business Setup Mode — everyone without bypass sees the Coming-Soon page
    // (including logged-in plain consumers).
    return <PublicHomeNewLookV2 comingSoon offerMonths={offerMonths} waitlistEnabled={waitlistEnabled} launchAt={launchAt} />;
  }
  if (!user) {
    // New Look V2 is the standard look — anonymous visitors get the premium
    // V2 public landing so login just unlocks the personalized same product.
    // Admin/QA can preview the legacy landing via ?design=classic_b|legacy.
    return designVariant === "new_look_v2" ? <PublicHomeNewLookV2 /> : <Landing />;
  }
  return designVariant === "new_look_v2" ? <HomeNewLookV2 />
    : designVariant === "classic_b" ? <HomeB /> : <Home />;
}

// `/pricing` is a single URL with two faces:
//   • anon listeners → the marketing 3-tier compare page
//   • logged-in users → the existing checkout-aware billing page
// Internal Links like Radio's "Go Premium" expect checkout flow, so
// they get the original component once authed.
export function PricingGate() {
  const { user, loading } = _useAuth_();
  if (loading) return null;
  return user ? <Pricing /> : <MarketingPricing />;
}

// Phase R.1 — Stub component for the new /pay, /discover, /coupon/:id
// routes.  In legacy variant they render this friendly hint; in FUUSIC
// variant, FUUSICOverlay covers the page with the real screen.
export function FUUSICStubPage({ title, hint }) {
  const setVariant = useDesignVariantStore((s) => s.setVariant);
  return (
    <div className="min-h-[60vh] flex items-center justify-center px-6"
              data-testid="rl-stub-page">
      <div className="max-w-sm w-full bg-bg-elevated border border-white/[0.06]
                              rounded-2xl p-6 text-center">
        <div className="text-[11px] font-mono uppercase tracking-widest
                                text-accent-electric">FUUSIC · Phase R.1</div>
        <div className="text-lg font-display font-bold mt-1">{title}</div>
        <p className="text-sm text-text-secondary mt-2">{hint}</p>
        <button
          type="button"
          onClick={() => setVariant("radiolife")}
          data-testid="rl-stub-enable-btn"
          className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 rounded-full
                              bg-accent-electric/15 text-accent-electric text-sm
                              font-semibold uppercase tracking-wider
                              hover:bg-accent-electric/25 transition-colors">
          ✨ Enable FUUSIC
        </button>
      </div>
    </div>
  );
}