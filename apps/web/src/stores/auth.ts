/**
 * Auth / current-user store — the ONLY server-state in Pinia (spec: the rest
 * of the server data lives in TanStack Query). The access token itself stays
 * in the api-client memory store; session persistence is the HttpOnly cookie.
 */
import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { memoryTokenStore, type User } from '@lexoria/api-client';
import { api } from '@/lib/api';
import { emitSessionEvent, onSessionEvent } from '@/lib/session';

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null);
  /** True once the boot-time session probe has finished. */
  const ready = ref(false);

  // Keep the store in sync when the shared client decides the session died
  // (single-flight refresh failed). The token store is already cleared there.
  onSessionEvent('expired', () => {
    user.value = null;
    ready.value = true;
  });

  const loggedIn = computed(() => user.value !== null);

  let probing: Promise<User | null> | null = null;

  /**
   * Boot / guard entry point. With a token or a still-valid refresh cookie a
   * `me` call succeeds (healing via the client's single-flight refresh);
   * otherwise we stay logged out. Concurrent callers share one probe.
   */
  function ensureSession(): Promise<User | null> {
    if (user.value) return Promise.resolve(user.value);
    if (probing) return probing;
    probing = (async () => {
      try {
        user.value = await api.me.get();
      } catch {
        user.value = null;
      } finally {
        ready.value = true;
        probing = null;
      }
      return user.value;
    })();
    return probing;
  }

  async function login(identifier: string, password: string): Promise<User> {
    const session = await api.auth.login({ identifier, password });
    memoryTokenStore.write(session.access_token);
    user.value = session.user;
    ready.value = true;
    return session.user;
  }

  async function register(username: string, email: string, password: string): Promise<User> {
    await api.auth.register({ username, email, password });
    // Registration does not return a session per contract → log straight in.
    return login(username, password);
  }

  async function logout(): Promise<void> {
    user.value = null;
    ready.value = true;
    memoryTokenStore.clear();
    emitSessionEvent('expired'); // re-entrant handlers are idempotent
    try {
      await api.auth.logout();
    } catch {
      // Cookie clearing is best-effort; local session is already gone.
    }
  }

  function clearUser(): void {
    user.value = null;
    memoryTokenStore.clear();
  }

  return { user, ready, loggedIn, ensureSession, login, register, logout, clearUser };
});
