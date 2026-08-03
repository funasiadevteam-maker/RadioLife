import api, { API_BASE } from './client';

/* ── Podcast API layer ─────────────────────────────────────────── */

export async function discoverChannels(q?: string, category?: string) {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (category) params.set('category', category);
  const r = await api.get(`/podcasts/discover?${params.toString()}`);
  return r.data?.channels || [];
}

export async function getChannel(channelId: string) {
  const r = await api.get(`/podcasts/channels/${channelId}`);
  return r.data; // { channel, episodes, followers }
}

export async function getChannelHighlights(channelId: string, limit = 10) {
  const r = await api.get(`/podcasts/channels/${channelId}/highlights?limit=${limit}`);
  return r.data?.items || [];
}

export async function getEpisode(epId: string) {
  const r = await api.get(`/podcasts/episodes/${epId}`);
  return r.data;
}

export async function getEpisodeMagicClips(epId: string) {
  const r = await api.get(`/podcasts/episodes/${epId}/magic-clips`);
  return r.data?.items || [];
}

export async function getEpisodeShoppableCards(epId: string) {
  const r = await api.get(`/podcasts/episodes/${epId}/shoppable-cards`);
  return r.data?.items || [];
}

export function shoppableClickUrl(cardId: string) {
  return `${API_BASE}/podcasts/shoppable-cards/${cardId}/click`;
}

export async function getGlobalHighlights(limit = 20, cursor?: string | null) {
  let url = `/podcasts/highlights?limit=${limit}`;
  if (cursor) url += `&cursor=${encodeURIComponent(cursor)}`;
  const r = await api.get(url);
  return r.data; // { items, next_cursor, has_more }
}

export async function subscribe(channelId: string) {
  // Fire funnel event first (best-effort)
  api.post(`/podcasts/channels/${channelId}/funnel/cta-clicked`).catch(() => {});
  const r = await api.post(`/podcasts/channels/${channelId}/subscribe`);
  return r.data; // { checkout_url }
}

export async function getListenerSubscriptions() {
  const r = await api.get('/listener/subscriptions');
  return Array.isArray(r.data) ? r.data : [];
}

export async function cancelSubscription(lsubId: string) {
  const r = await api.post(`/listener/subscriptions/${lsubId}/cancel`);
  return r.data;
}

export async function resumeSubscription(lsubId: string) {
  const r = await api.post(`/listener/subscriptions/${lsubId}/resume`);
  return r.data;
}

export function episodeAudioUrl(epId: string) {
  return `${API_BASE}/podcasts/episodes/${epId}/audio.mp3`;
}

/* ── Creator-side APIs (Phase 36f Turn 2) ─────────────────────── */

export async function getCreatorMe() {
  const r = await api.get('/podcasts/creators/me');
  return r.data; // { creator, id, ... }
}

export async function applyAsCreator(form: {
  display_name: string; bio: string; contact_email: string; market: string;
}) {
  const r = await api.post('/podcasts/creators/apply', form);
  return r.data;
}

export async function getCreatorChannels(creatorId: string) {
  const r = await api.get(`/podcasts/creators/${creatorId}/channels`);
  return r.data?.channels || [];
}

export async function getChannelSettings(channelId: string) {
  const r = await api.get(`/podcasts/channels/${channelId}/settings`);
  return r.data;
}

export async function patchChannelSettings(channelId: string, body: {
  magic_clips_enabled?: boolean; magic_clips_per_episode?: number;
}) {
  const r = await api.patch(`/podcasts/channels/${channelId}/settings`, body);
  return r.data;
}

export async function getLightningSplits(channelId: string) {
  const r = await api.get(`/podcasts/channels/${channelId}/lightning-splits`);
  return r.data;
}

export async function putLightningSplits(channelId: string, recipients: any[]) {
  const r = await api.put(`/podcasts/channels/${channelId}/lightning-splits`, { recipients });
  return r.data;
}

export async function getStripeAccount(creatorId: string) {
  try {
    const r = await api.get(`/creators/${creatorId}/stripe-account`);
    return r.data;
  } catch (e: any) {
    if (e?.response?.status === 404) return null;
    throw e;
  }
}

export async function createStripeAccount(creatorId: string) {
  const r = await api.post(`/creators/${creatorId}/stripe-account`, {});
  return r.data;
}

export async function getStripeOnboardingLink(creatorId: string) {
  const r = await api.post(`/creators/${creatorId}/stripe-account/onboarding-link`, {});
  return r.data; // { url }
}

export async function getSubscriptionPlan(channelId: string) {
  try {
    const r = await api.get(`/podcasts/channels/${channelId}/subscription-plan`);
    return r.data;
  } catch { return null; }
}

export async function createSubscriptionPlan(channelId: string, body: {
  name: string; price_cents: number; trial_days: number;
}) {
  const r = await api.post(`/podcasts/channels/${channelId}/subscription-plan`, body);
  return r.data;
}

export async function patchSubscriptionPlan(channelId: string, body: { active?: boolean }) {
  const r = await api.patch(`/podcasts/channels/${channelId}/subscription-plan`, body);
  return r.data;
}

export async function publishMagicClip(clipId: string) {
  const r = await api.post(`/podcasts/magic-clips/${clipId}/publish`);
  return r.data;
}

export async function patchMagicClip(clipId: string, body: { title?: string }) {
  const r = await api.patch(`/podcasts/magic-clips/${clipId}`, body);
  return r.data;
}

export async function deleteMagicClip(clipId: string) {
  const r = await api.delete(`/podcasts/magic-clips/${clipId}`);
  return r.data;
}

export async function getNudgeStatus(creatorId: string) {
  try {
    const r = await api.get(`/podcasts/creators/${creatorId}/nudge-status`);
    return r.data;
  } catch { return null; }
}

export async function pauseNudges(creatorId: string) {
  const r = await api.post(`/podcasts/creators/${creatorId}/nudge-status/pause`, {});
  return r.data;
}

export async function getFunnelSummary(creatorId: string, days = 7) {
  const r = await api.get(`/podcasts/creators/${creatorId}/funnel/summary?window_days=${days}`);
  return r.data;
}

export async function getFunnelDaily(creatorId: string, days = 7) {
  const r = await api.get(`/podcasts/creators/${creatorId}/funnel/daily?days=${days}`);
  return r.data;
}

export async function createChannel(creatorId: string, body: {
  title: string; description: string; category: string;
  language: string; script_preference: string;
}) {
  const r = await api.post(`/podcasts/creators/${creatorId}/channels`, body);
  return r.data;
}

export async function getChannelEpisodes(channelId: string, includeDrafts = true) {
  const r = await api.get(`/podcasts/channels/${channelId}/episodes?include_drafts=${includeDrafts}`);
  return r.data?.episodes || [];
}

export async function getChannelSubscriptionStatus(channelId: string) {
  try {
    const r = await api.get(`/podcasts/channels/${channelId}/subscription-status`);
    return r.data;
  } catch { return null; }
}

export async function subscribeToChannel(channelId: string) {
  api.post(`/podcasts/channels/${channelId}/funnel/cta-clicked`).catch(() => {});
  const r = await api.post(`/podcasts/channels/${channelId}/subscribe`);
  return r.data; // { checkout_url }
}
