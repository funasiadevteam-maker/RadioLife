// AI-generated branded game cover art (FUUSIC premium Play & Win set).
// Keyed by canonical game type; `gameArtFor()` maps the many type /
// template aliases used across the app onto one of these.
// NOTE: kept in sync with the web set in frontend/src/assets/gameArt.js.
const CDN = 'https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images';

export const GAME_ART: Record<string, string> = {
  spin_win: `${CDN}/20e325e4d4cfee6ecff95a22d9123eb63288cfb5ee113e15039318de3413a3af.jpeg`,
  lucky_dice: `${CDN}/a13408cf1fd1c68d490f964e6fccc9b7dd1fc2c8f7cf89c47794bc5004f55d98.jpeg`,
  scratch_win: `${CDN}/74ccfab3b6e15ff9c137fa130aac9adad35e9f4592555e2a321030a40b8894b6.jpeg`,
  trivia: `${CDN}/deeece2eb7edb09d10ca665d9e776a99f3dd94c79f60ec5a4f3a290c256e86b3.jpeg`,
  predict: `${CDN}/d5e300ff838b99bdb46e22b6f922e7cd6c8c12bd17a30339c3cb9ad9e399668a.jpeg`,
  quiz: `${CDN}/e289bd0a62acac71e1ce74aee6cc0c606cbfc786dc3f0dd870edb8a4bf63a848.jpeg`,
  slot_machine: `${CDN}/eb6678ee3fa69fb41494a1a1246512d61121c154ecaf27e7af58af89457d4bf3.jpeg`,
  memory_match: `${CDN}/988ccd267a988a67431b0f4c49fd10b8b4283c7457af80ad56254425cada49df.jpeg`,
  word_puzzle: `${CDN}/afb8e62a5e3ac3a5417c6ce605e7a0c0294b321d66088677fb8176faca7ddbb8.jpeg`,
  mystery_box: `${CDN}/90edbaba32fdecb6446f2aba757b6328f4b171ab6560903b84026a02df4ab6db.jpeg`,
};

// Large hero / stage backdrops (used by Play Home + the wheel / dice stages).
export const GAME_HERO = `${CDN}/039b9629d4e19c5e32d5ec2eb07eb982083a4fab93bf5644de44a00fbfec3d5b.jpeg`;
export const WHEEL_BACKDROP = `${CDN}/fbb9348a04fbd336cbbf215849418de5ff5fd002b25dfa58c156e0f56cc860ca.jpeg`;
export const DICE_STAGE = `${CDN}/e1ca2215e43a2a2a218d3bf077d02ed93a951bb39407dd8edb366fd37fa9b277.jpeg`;

const ALIASES: Record<string, string> = {
  spin_win: 'spin_win', spin: 'spin_win', spin_wheel: 'spin_win', tpl_spin_wheel: 'spin_win',
  lucky_dice: 'lucky_dice', dice: 'lucky_dice', dining_dice: 'lucky_dice', tpl_dice: 'lucky_dice',
  scratch_win: 'scratch_win', scratch: 'scratch_win', scratch_card: 'scratch_win', tpl_scratch_card: 'scratch_win',
  trivia: 'trivia', music_trivia: 'trivia', tpl_trivia: 'trivia',
  lyric: 'trivia', lyric_hunt: 'trivia', guess_the_lyric: 'trivia',
  predict: 'predict', predict_win: 'predict', prediction: 'predict', predictions: 'predict',
  quiz: 'quiz', tpl_quiz: 'quiz',
  slot_machine: 'slot_machine', slots: 'slot_machine', tpl_slot_machine: 'slot_machine',
  memory_match: 'memory_match', memory: 'memory_match', tpl_memory_match: 'memory_match',
  word_puzzle: 'word_puzzle', word: 'word_puzzle', tpl_word_puzzle: 'word_puzzle',
  mystery_box: 'mystery_box', mystery: 'mystery_box', tpl_mystery_box: 'mystery_box',
  pick_a_card: 'mystery_box', tpl_pick_a_card: 'mystery_box',
};

// Return the best cover art URL for any of the passed type/template keys.
export function gameArtFor(...keys: (string | undefined | null)[]): string {
  for (const k of keys) {
    if (!k) continue;
    const norm = String(k).toLowerCase();
    const canonical = ALIASES[norm] || (GAME_ART[norm] ? norm : '');
    if (canonical && GAME_ART[canonical]) return GAME_ART[canonical];
  }
  return GAME_ART.spin_win;
}

export default GAME_ART;
