<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { messageOf } from '@lexoria/api-client';
import { useAuthStore } from '@/stores/auth';
import { useUiStore } from '@/stores/ui';
import Icon from '@/components/Icon.vue';

const auth = useAuthStore();
const ui = useUiStore();
const route = useRoute();
const router = useRouter();

const account = ref('');
const password = ref('');
const error = ref('');
const busy = ref(false);

const redirect = computed(() => (typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'));

onMounted(() => {
  if (auth.loggedIn) void router.replace(redirect.value);
});

async function submit(): Promise<void> {
  error.value = '';
  if (!account.value.trim() || !password.value) {
    error.value = '请输入账号与密码';
    return;
  }
  busy.value = true;
  try {
    await auth.login(account.value.trim(), password.value);
    void router.replace(redirect.value);
  } catch (err) {
    error.value = messageOf(err);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-dvh items-center justify-center bg-stone-100 px-4 dark:bg-stone-950">
    <div class="w-full max-w-sm">
      <div class="mb-6 flex items-center gap-2.5 justify-center">
        <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-orange-600 text-lg font-black text-white dark:bg-orange-500 dark:text-stone-950">L</span>
        <div>
          <p class="text-lg leading-5 font-bold tracking-tight">Lexiora</p>
          <p class="text-xs text-stone-500 dark:text-stone-400">词汇学习工作台</p>
        </div>
      </div>

      <form class="panel space-y-4 p-6" @submit.prevent="submit">
        <div>
          <label class="microlabel mb-1 block" for="login-account">用户名或邮箱</label>
          <input
            id="login-account"
            v-model="account"
            class="field"
            placeholder="username 或 email"
            autocomplete="username"
            spellcheck="false"
          />
        </div>
        <div>
          <label class="microlabel mb-1 block" for="login-password">密码</label>
          <input id="login-password" v-model="password" class="field" type="password" autocomplete="current-password" />
        </div>

        <p v-if="error" class="rounded-md bg-red-50 px-2.5 py-2 text-[13px] text-red-700 dark:bg-red-950/50 dark:text-red-300" role="alert">
          {{ error }}
        </p>

        <button type="submit" class="btn-primary w-full" :disabled="busy">
          <span v-if="busy" class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
          <span v-else class="flex items-center gap-1.5"><Icon name="logout" :size="14" class="rotate-180" />登录</span>
        </button>

        <p class="text-center text-[13px] text-stone-500 dark:text-stone-400">
          还没有账号？
          <RouterLink class="link" :to="{ name: 'register', query: redirect !== '/dashboard' ? { redirect: redirect } : {} }">注册</RouterLink>
        </p>
      </form>

      <div class="mt-4 flex items-center justify-center gap-2 text-[11px] text-stone-400 dark:text-stone-600">
        <button type="button" class="flex items-center gap-1 hover:text-stone-600 dark:hover:text-stone-400" @click="ui.toggleTheme()">
          <Icon :name="ui.isDark ? 'sun' : 'moon'" :size="12" />
          {{ ui.isDark ? '浅色' : '深色' }}主题
        </button>
      </div>
    </div>
  </div>
</template>
