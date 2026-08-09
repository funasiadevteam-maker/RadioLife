// Phase RWD.1 — shared icon map for earn actions/missions (web, lucide).
import React from "react";
import {
  Radio, KeyRound, Brain, Target, Gamepad2, MapPin, CreditCard,
  Share2, UserPlus, Compass, Coins, Sparkles,
} from "lucide-react";

const MAP = {
  radio: Radio,
  key: KeyRound,
  brain: Brain,
  target: Target,
  gamepad: Gamepad2,
  "map-pin": MapPin,
  "credit-card": CreditCard,
  share: Share2,
  "user-plus": UserPlus,
  compass: Compass,
  coins: Coins,
};

export function EarnIcon({ name, size = 16, className = "" }) {
  const Cmp = MAP[name] || Sparkles;
  return <Cmp size={size} className={className} />;
}
