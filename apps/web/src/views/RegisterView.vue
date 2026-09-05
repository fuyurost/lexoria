<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { messageOf } from '@lexoria/api-client';
import { useAuthStore } from '@/stores/auth';
import Icon from '@/components/Icon.vue';

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const username = ref('');
const email = ref('');
const password = ref('');
const confirm = ref('');
const error = ref('');
const busy = ref(false);

const redirect = computed(() => (typeof route.query.redirect === 'string' ? route.query.redirect : '/dashboard'));

function validate(): string {
  if (username.value.trim().length < 2) return '用户名至少 2 个字符';
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) return '邮箱格式不正确';
  if (password.value.length < 6) return '密码至少 6 位';
  if (password.value !== confirm.value) return '两次输入的密码不一致';
  return '';
}

async function submit(): Promise<void> {
  error.value = '';
  const problem = validate();
  if (problem) {
    error.value = problem;
    return;
  }
  busy.value = true;
  try {
    await auth.register(username.value.trim(), email.value.trim(), password.value);
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
        <p class="text-lg font-bold tracking-tight">创建 Lexiora 账号</p>
      </div>

      <form class="panel space-y-4 p-6" @submit.prevent="submit">
        <div>
          <label class="microlabel mb-1 block" for="reg-username">用户名</label>
          <input id="reg-username" v-model="username" class="field" autocomplete="username" spellcheck="false" />
        </div>
        <div>
          <label class="microlabel mb-1 block" for="reg-email">邮箱</label>
          <input id="reg-email" v-model="email" class="field" type="email" autocomplete="email" spellcheck="false" />
        </div>
        <div>
          <label class="microlabel mb-1 block" for="reg-password">密码</label>
          <input id="reg-password" v-model="password" class="field" type="password" autocomplete="new-password" />
        </div>
        <div>
          <label class="microlabel mb-1 block" for="reg-confirm">确认密码</label>
          <input id="reg-confirm" v-model="confirm" class="field" type="password" autocomplete="new-password" />
        </div>

        <p v-if="error" class="rounded-md bg-red-50 px-2.5 py-2 text-[13px] text-red-700 dark:bg-red-950/50 dark:text-red-300" role="alert">
          {{ error }}
        </p>

        <button type="submit" class="btn-primary w-full" :disabled="busy">
          <span v-if="busy" class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
          <span v-else class="flex items-center gap-1.5"><Icon name="plus" :size="14" />注册并登录</span>
        </button>

        <p class="text-center text-[13px] text-stone-500 dark:text-stone-400">
          已有账号？
          <RouterLink class="link" :to="{ name: 'login', query: redirect !== '/dashboard' ? { redirect: redirect } : {} }">直接登录</RouterLink>
        </p>
      </form>
    </div>
  </div>
</template>
