<script setup lang="ts">
import type { SenseDraft } from '@/lib/senseDraft';
import { POS_SUGGESTIONS } from '@/lib/senseDraft';

const props = defineProps<{ value: SenseDraft; compact?: boolean }>();
const emit = defineEmits<{ 'update:value': [value: SenseDraft] }>();

function patch(field: keyof SenseDraft, v: string): void {
  emit('update:value', { ...props.value, [field]: v });
}
</script>

<template>
  <div class="grid gap-2" :class="compact ? 'grid-cols-[110px_1fr]' : 'grid-cols-1 sm:grid-cols-[140px_1fr]'">
    <div class="contents">
      <label class="microlabel flex items-center" :class="compact ? '!text-[10px]' : ''">词性</label>
      <input
        :value="value.part_of_speech"
        class="field"
        :class="compact ? '!h-7 !text-[13px]' : ''"
        list="pos-suggestions"
        placeholder="n. / v. …"
        @input="patch('part_of_speech', ($event.target as HTMLInputElement).value)"
      />
    </div>
    <div class="contents">
      <label class="microlabel flex items-center" :class="compact ? '!text-[10px]' : ''">
        中文释义
      </label>
      <input
        :value="value.definition_zh"
        class="field"
        :class="compact ? '!h-7 !text-[13px]' : ''"
        placeholder="中文释义（中英至少填一项）"
        @input="patch('definition_zh', ($event.target as HTMLInputElement).value)"
      />
    </div>
    <div class="contents">
      <label class="microlabel flex items-center" :class="compact ? '!text-[10px]' : ''">
        英文释义
      </label>
      <input
        :value="value.definition_en"
        class="field"
        :class="compact ? '!h-7 !text-[13px]' : ''"
        placeholder="English definition（可选）"
        @input="patch('definition_en', ($event.target as HTMLInputElement).value)"
      />
    </div>
    <datalist id="pos-suggestions">
      <option v-for="p in POS_SUGGESTIONS" :key="p" :value="p" />
    </datalist>
  </div>
</template>
