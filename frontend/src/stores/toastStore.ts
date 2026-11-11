import { create } from "zustand";

export type ToastVariant = "success" | "error" | "info";

export interface ToastAction {
  label: string;
  onClick: () => void;
}

export interface Toast {
  id: number;
  variant: ToastVariant;
  message: string;
  action?: ToastAction;
}

export interface PushOptions {
  action?: ToastAction;
  /** Defaults to 4000; an actionable toast (e.g. "Undo") usually wants longer. */
  durationMs?: number;
}

let nextId = 1;

interface ToastState {
  toasts: Toast[];
  push: (variant: ToastVariant, message: string, options?: PushOptions) => void;
  dismiss: (id: number) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (variant, message, options) => {
    const id = nextId++;
    set((s) => ({ toasts: [...s.toasts, { id, variant, message, action: options?.action }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), options?.durationMs ?? 4000);
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export const toast = {
  success: (message: string, options?: PushOptions) => useToastStore.getState().push("success", message, options),
  error: (message: string, options?: PushOptions) => useToastStore.getState().push("error", message, options),
  info: (message: string, options?: PushOptions) => useToastStore.getState().push("info", message, options),
};
