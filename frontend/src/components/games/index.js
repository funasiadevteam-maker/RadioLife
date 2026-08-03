// Phase 23 Session 4 — per-template subcomponent barrel.
// Phase 23 Session 4.5e — legacy `games/ScratchCard.js` deleted; the
// only ScratchCard implementation is the CSS-mask one in this dir.
// Per-template theming constant added so listener tiles + wizard
// picker share one visual language.
import SpinWheel    from "./SpinWheelGame";
import ScratchCardCouponTools from "./ScratchCardGame";
import Quiz          from "../../games/Quiz";
import MysteryBox  from "./MysteryBoxGame";
import SlotMachine from "./SlotMachineGame";
import MemoryMatch from "../../games/MemoryMatch";
import WordPuzzle  from "../../games/WordPuzzle";
import PickACardGame from "./PickACardGame";

export const SpinWheelGame    = SpinWheel;
export const ScratchCardGame = ScratchCardCouponTools;
export const TriviaQuizGame  = Quiz;
export const MysteryBoxGame  = MysteryBox;
export const SlotMachineGame = SlotMachine;
export const MemoryMatchGame = MemoryMatch;
export const WordPuzzleGame  = WordPuzzle;
export { PickACardGame };

export const LISTENER_VISIBLE_TEMPLATES = [
  "tpl_spin_wheel",
  "tpl_scratch_card",
  "tpl_quiz",
  "tpl_mystery_box",
  "tpl_pick_a_card",
  "tpl_slot_machine",
];

// Phase 23 Session 4.5e — per-template visual identity.  Locked palette
// so the listener tiles, the wizard step-1 picker, and any future
// surface (search results, recommendations) share one language.
// Brand colour from `campaign.brand_colors_json.primary` is still
// shown as a secondary corner swatch — advertisers keep brand
// presence without overriding category identity.
export const TEMPLATE_THEME = {
  spin_wheel:    { accent: "#a855f7", emoji: "🎡", label: "Spin Wheel" },
  scratch_card: { accent: "#10b981", emoji: "🎟️", label: "Scratch Card" },
  quiz:                  { accent: "#3b82f6", emoji: "🧠", label: "Trivia Quiz" },
  mystery_box:    { accent: "#f59e0b", emoji: "🎁", label: "Mystery Box" },
  pick_a_card:    { accent: "#ec4899", emoji: "🃏", label: "Pick a Card" },
  // Hidden-but-functional fallbacks.
  slot_machine: { accent: "#6366f1", emoji: "🎰", label: "Slot Machine" },
  memory_match: { accent: "#14b8a6", emoji: "🧩", label: "Memory Match" },
  word_puzzle:    { accent: "#84cc16", emoji: "✒️", label: "Word Puzzle" },
};

// Convenience: accept either a `template_id` ("tpl_scratch_card") or
// a `game_type` ("scratch_card") string and return the theme entry.
// Returns a sensible neutral default for unknown values so callers
// don't crash on legacy campaigns missing the field.
export function themeFor(templateOrType) {
  if (!templateOrType) return _DEFAULT_THEME;
  const key = templateOrType.startsWith("tpl_")
    ? templateOrType.slice(4)
    : templateOrType;
  return TEMPLATE_THEME[key] || _DEFAULT_THEME;
}
const _DEFAULT_THEME = { accent: "#64748b", emoji: "🎮", label: "Game" };

// Dispatcher: render_config.type ⇒ component.
export const GAME_DISPATCH = {
  spin_wheel:      SpinWheelGame,
  scratch_card:  ScratchCardGame,
  quiz:              TriviaQuizGame,
  mystery_box:    MysteryBoxGame,
  pick_a_card:    PickACardGame,
  slot_machine:  SlotMachineGame,
  memory_match:  MemoryMatchGame,
  word_puzzle:    WordPuzzleGame,
};
