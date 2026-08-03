import { create } from 'zustand';

export type GateAccess = {
  code?: string;
  required_tier?: string;
  current_tier?: string;
  upgrade_path?: string;
  channel?: string;
  channel_name?: string;
  unlock_message?: string;
  message?: string;
  cta?: {
    label?: string;
    href?: string;
    required_level?: number;
    points_needed?: number;
    current_points?: number;
    required_points?: number;
  };
};

type GateChannel = {
  slug?: string;
  name?: string;
};

type GateState = {
  visible: boolean;
  access: GateAccess | null;
  channel: GateChannel | null;
  openGate: (access: GateAccess, channel?: GateChannel) => void;
  closeGate: () => void;
};

export const useGateStore = create<GateState>((set) => ({
  visible: false,
  access: null,
  channel: null,
  openGate: (access, channel) => set({ visible: true, access, channel: channel || null }),
  closeGate: () => set({ visible: false, access: null, channel: null }),
}));
