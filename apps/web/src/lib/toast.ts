import { reactive } from 'vue';

export type ToastKind = 'success' | 'error' | 'info';

export interface ToastItem {
  id: number;
  kind: ToastKind;
  text: string;
}

interface ToastState {
  list: ToastItem[];
}

const state = reactive<ToastState>({ list: [] });
let seq = 0;

const DURATION_MS = 4200;

export function toast(text: string, kind: ToastKind = 'info'): void {
  const id = ++seq;
  state.list.push({ id, kind, text });
  window.setTimeout(() => dismiss(id), DURATION_MS);
}

export function toastSuccess(text: string): void {
  toast(text, 'success');
}

export function toastError(text: string): void {
  toast(text, 'error');
}

export function dismiss(id: number): void {
  const idx = state.list.findIndex((t) => t.id === id);
  if (idx >= 0) state.list.splice(idx, 1);
}

export function useToasts(): ToastState {
  return state;
}
