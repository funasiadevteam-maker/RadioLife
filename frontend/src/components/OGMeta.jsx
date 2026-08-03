// Phase 42-E2.4 — Universal Open Graph meta-tag injection.
//
// Drop <OGMeta entityType="station" entityId={slug} title="…" description="…"/>
// on any shareable route to expose the OG card + Twitter Card preview
// for that surface.  The OG image URL hits our /api/og-card/<type>/<id>
// endpoint which dynamically renders a 1200×630 PNG.
//
// Crawlers (Twitter/X, Facebook, LinkedIn, Slack, Discord, WhatsApp)
// will fetch the OG image when the canonical page URL is pasted into
// their input boxes.  React's lack of SSR is fine here — all major
// social crawlers support runtime-rendered <meta> tags.

import React from "react";
import { Helmet } from "react-helmet-async";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

function buildCardUrl(entityType, entityId) {
  const safeType = encodeURIComponent(entityType);
  const safeId   = encodeURIComponent(entityId || "x");
  return `${BACKEND_URL}/api/og-card/${safeType}/${safeId}`;
}

function currentPageUrl() {
  if (typeof window === "undefined") return BACKEND_URL;
  return window.location.href;
}

export default function OGMeta({
  entityType,
  entityId = "x",
  title,
  description,
  url,            // optional canonical override
}) {
  const cardUrl = buildCardUrl(entityType, entityId);
  const pageUrl = url || currentPageUrl();
  const safeTitle      = (title || "BigFM").slice(0, 120);
  const safeDesc        = (description || "Personalized radio, news, "
                                                  + "games and rewards on BigFM.").slice(0, 200);
  return (
    <Helmet prioritizeSeoTags>
      <title>{safeTitle}</title>
      <meta name="description" content={safeDesc} />

      {/* Open Graph */}
      <meta property="og:type" content="website" />
      <meta property="og:site_name" content="BigFM" />
      <meta property="og:title" content={safeTitle} />
      <meta property="og:description" content={safeDesc} />
      <meta property="og:image" content={cardUrl} />
      <meta property="og:image:width" content="1200" />
      <meta property="og:image:height" content="630" />
      <meta property="og:url" content={pageUrl} />

      {/* Twitter Card */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={safeTitle} />
      <meta name="twitter:description" content={safeDesc} />
      <meta name="twitter:image" content={cardUrl} />
    </Helmet>
  );
}
