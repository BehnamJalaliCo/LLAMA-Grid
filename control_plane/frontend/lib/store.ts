"use client";

import { create } from "zustand";

type View = "overview" | "chat" | "models" | "servers" | "providers" | "deployments" | "keys";

type PanelState = {
  view: View;
  setView: (view: View) => void;
};

export const usePanelStore = create<PanelState>((set) => ({
  view: "overview",
  setView: (view) => set({ view }),
}));
