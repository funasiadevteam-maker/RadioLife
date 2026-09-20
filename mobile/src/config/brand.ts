// FUUSIC — central consumer brand config for the mobile app (single source of truth).
// Technical identifiers (bundle IDs, bigfm_session, /api routes, bigfm:* events)
// are intentionally NOT renamed — see FUUSIC_REBRAND_TECHDEBT.md.
export const BRAND = {
  name: 'FUUSIC',
  tagline: 'Everything You Love, Together.',
  descriptor: 'Listen · Connect · Play · Shop · Earn',
  descriptorWords: ['Listen', 'Connect', 'Play', 'Shop', 'Earn'],
  meaning: [
    ['F', 'Friends'],
    ['U', 'Unite'],
    ['U', 'Unique Experiences'],
    ['S', 'Social'],
    ['I', 'Interaction'],
    ['C', 'Commerce'],
  ] as [string, string][],
  meaningLine:
    'Friends · Unite · Unique Experiences · Social · Interaction · Commerce',
  supportEmail: 'support@fuusic.com',
  domain: 'fuusic.com',
  businessName: 'FUUSIC Business',
  premiumName: 'FUUSIC Premium',
  socialName: 'FUUSIC Social',
  liveName: 'FUUSIC Live',
};

export default BRAND;
