// FUUSIC — central consumer brand config (single source of truth).
// Components read from here so the brand can be swapped without touching UI.
// NOTE: This is the CONSUMER brand. Technical identifiers (bigfm_session,
// the `radiolife` design-variant key, /api routes, DB collections, bigfm:*
// events) are intentionally NOT renamed — see FUUSIC_REBRAND_TECHDEBT.md.
export const BRAND = {
  name: "FUUSIC",
  legalNote: "FUUSIC",
  tagline: "Everything You Love, Together.",
  descriptor: "Listen · Connect · Play · Shop · Earn",
  descriptorWords: ["Listen", "Connect", "Play", "Shop", "Earn"],
  meaning: [
    ["F", "Friends"],
    ["U", "Unite"],
    ["U", "Unique Experiences"],
    ["S", "Social"],
    ["I", "Interaction"],
    ["C", "Commerce"],
  ],
  meaningLine:
    "Friends · Unite · Unique Experiences · Social · Interaction · Commerce",
  supportEmail: "support@radiolife.app",
  domain: "fuusic.com",
  webUrl: (process.env.REACT_APP_PUBLIC_WEB_URL || "").replace(/\/$/, ""),
  businessName: "FUUSIC Business",
  premiumName: "FUUSIC Premium",
  socialName: "FUUSIC Social",
  liveName: "FUUSIC Live",
  ogImage: "/fuusic-og.png",
};

export default BRAND;
