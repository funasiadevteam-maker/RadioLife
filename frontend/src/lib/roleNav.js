// Phase 19a — Discoverability: role-based nav gating.
//
// Reads `user.role` from useAuth(). Capability gates are intentionally
// permissive at the UI layer — the actual API enforcement lives in
// ProtectedRoute + the backend require_admin / advertiser-ownership checks.
// This file only decides what to surface in the chrome.

import { useAuth } from "@/AuthContext";

export function useRoleNav() {
  const { user } = useAuth();
  const role = user?.role || "listener";
  const canAdmin       = role === "admin";
  // "creator-capable" = admin or creator role. Ownership-driven gating
  // (db.podcast_creators lookup) is a follow-up.
  const canCreator     = canAdmin || role === "creator";
  // Same shape for advertiser. Ownership comes from /api/advertiser/me but
  // that fetch happens inside the Advertiser shell; the nav entry is enough.
  const canAdvertiser  = canAdmin || role === "advertiser";
  // Phase ADMOD.1 — Ad Manager role can review creatives.  Admin includes it.
  const canAdReview    = canAdmin || role === "ad_manager";
  return { user, role, canAdmin, canCreator, canAdvertiser, canAdReview };
}
