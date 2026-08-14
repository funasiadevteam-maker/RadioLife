// Slide-in product mini-cart open/close state (web).
import { create } from "zustand";

export const useMiniCart = create((set) => ({
  open: false,
  show: () => set({ open: true }),
  hide: () => set({ open: false }),
}));
