/**
 * Small UI-preferences store (theme, sidebar) + one transient flag used by
 * the app-shell keyboard shortcut. Everything else stays component-local.
 */
import { computed, ref, watch } from 'vue';
import { defineStore } from 'pinia';

export type Theme = 'light' | 'dark';

function readStoredTheme(): Theme {
  const stored = localStorage.getItem('lexoria.theme');
  if (stored === 'light' || stored === 'dark') return stored;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function readBool(key: string): boolean {
  return localStorage.getItem(key) === '1';
}

export const useUiStore = defineStore('ui', () => {
  const theme = ref<Theme>(readStoredTheme());
  /** Mobile drawer visibility; desktop ignores it. */
  const sidebarOpen = ref(false);
  const quickAddOpen = ref(false);

  const isDark = computed(() => theme.value === 'dark');

  function applyTheme(t: Theme): void {
    document.documentElement.classList.toggle('dark', t === 'dark');
    localStorage.setItem('lexoria.theme', t);
  }
  applyTheme(theme.value);
  watch(theme, (t) => applyTheme(t));

  const sidebarCollapsed = ref(readBool('lexoria.sidebar-collapsed'));
  watch(sidebarCollapsed, (v) => localStorage.setItem('lexoria.sidebar-collapsed', v ? '1' : '0'));

  function toggleTheme(): void {
    theme.value = theme.value === 'dark' ? 'light' : 'dark';
  }

  return { theme, isDark, sidebarOpen, sidebarCollapsed, quickAddOpen, toggleTheme };
});
