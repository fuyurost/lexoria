<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, provide } from 'vue';
import { RouterView, useRoute, useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';
import { useUiStore } from '@/stores/ui';
import { createNavBus, navBusKey } from '@/lib/navBus';
import { shouldIntercept } from '@/lib/keys';
import AppShell from '@/components/AppShell.vue';
import ToastHost from '@/components/ToastHost.vue';

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const ui = useUiStore();

const navBus = createNavBus();
provide(navBusKey, navBus);

const isPublic = computed(() => route.meta.public === true);

/** g + 单键导航表（键盘友好）。 */
const G_KEYS: Record<string, string> = {
  d: '/dashboard',
  i: '/inbox',
  w: '/words',
  r: '/review',
  s: '/sources',
  e: '/daily-sheets',
  t: '/settings',
};

let gAt = 0;

function onKeydown(e: KeyboardEvent): void {
  // Ctrl/Cmd + Shift + A — global Quick Add (works while typing too).
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'A' || e.key === 'a')) {
    e.preventDefault();
    if (auth.loggedIn) ui.quickAddOpen = !ui.quickAddOpen;
    return;
  }
  if (!shouldIntercept(e)) return;
  if (e.key === '/') {
    e.preventDefault();
    if (auth.loggedIn) {
      if (route.name !== 'words') void router.push('/words');
      navBus.searchTick += 1;
    }
    return;
  }
  if (e.key === 'g') {
    gAt = performance.now();
    return;
  }
  if (gAt > 0 && performance.now() - gAt < 900 && G_KEYS[e.key]) {
    e.preventDefault();
    const to = G_KEYS[e.key]!;
    gAt = 0;
    if (auth.loggedIn && route.path !== to) void router.push(to);
    return;
  }
  gAt = 0;
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown);
  // Warm the session probe early (cookie may already be valid).
  void auth.ensureSession();
});
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown);
});
</script>

<template>
  <AppShell v-if="!isPublic && auth.loggedIn" />
  <RouterView v-else />
  <ToastHost />
</template>
