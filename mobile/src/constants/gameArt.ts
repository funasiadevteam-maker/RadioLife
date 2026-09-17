// AI-generated branded game cover art (RadioLife dark-cinematic set).
// Keyed by canonical game type; `gameArtFor()` maps the many type /
// template aliases used across the app onto one of these.
export const GAME_ART: Record<string, string> = {
  spin_win: 'https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/5cc6c256215f175bfaf16886e6f22e5f657266aa95bedaa403c485bb1e10b598.jpeg',
  scratch_win: 'https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/6b5978039b43e8821ace062ba8cb55f09248f40ebb4bb6bcb647d26ae4c3a88b.jpeg',
  trivia: 'https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/6e72f2c14e1c53ddaddc70c3619bb3c3253d4a0706f8134763fa0c806fc10801.jpeg',
  lyric: 'https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/1bde050a3dd3d53b12ca61e4dd649ffb712d22570947810cbc8d0dec8c602756.jpeg',
  predict: 'https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/13c3918d07b885cc787eda074f1c5c9642bf9621372af1f3058b076f7a748f1a.jpeg',
  quiz: 'https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/fd9cb8b5bf6935d95999f4e6ddfaaa5005a88ca3318db339a824ed097f97819e.jpeg',
  slot_machine: 'https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/eb6678ee3fa69fb41494a1a1246512d61121c154ecaf27e7af58af89457d4bf3.jpeg',
  memory_match: 'https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/988ccd267a988a67431b0f4c49fd10b8b4283c7457af80ad56254425cada49df.jpeg',
  word_puzzle: 'https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/afb8e62a5e3ac3a5417c6ce605e7a0c0294b321d66088677fb8176faca7ddbb8.jpeg',
  mystery_box: 'https://static.prod-images.emergentagent.com/jobs/c58ec5fe-c3e5-4993-9aa8-87c91f8390aa/images/90edbaba32fdecb6446f2aba757b6328f4b171ab6560903b84026a02df4ab6db.jpeg',
};

const ALIASES: Record<string, string> = {
  spin_win: 'spin_win', spin: 'spin_win', spin_wheel: 'spin_win', tpl_spin_wheel: 'spin_win',
  scratch_win: 'scratch_win', scratch: 'scratch_win', scratch_card: 'scratch_win', tpl_scratch_card: 'scratch_win',
  trivia: 'trivia', music_trivia: 'trivia', tpl_trivia: 'trivia',
  lyric: 'lyric', lyric_hunt: 'lyric', guess_the_lyric: 'lyric',
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
