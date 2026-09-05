<script setup lang="ts">
/**
 * 练习纸预览渲染：
 *  - 服务端返回 HTML 字符串 → iframe srcdoc 安全展示（sandbox，无脚本）；
 *  - 服务端返回结构化 DTO → 直接排版渲染。
 */
import { computed } from 'vue';
import type { DailySheetPreview } from '@lexoria/api-client';
import Icon from './Icon.vue';

const props = defineProps<{ preview: DailySheetPreview | null; html: string | null }>();

const hasContent = computed(() => (props.preview && props.preview.sections.length > 0) || Boolean(props.html));

function paperClass(): string {
  if (!props.preview) return '';
  const size = props.preview.config.paper_size;
  if (size === 'a4') return 'aspect-[210/297]';
  return 'aspect-[148/210]';
}
</script>

<template>
  <div>
    <div v-if="!preview && !html" class="panel flex flex-col items-center gap-2 px-6 py-10 text-center text-sm text-stone-400">
      <Icon name="file" :size="22" />
      <p>点击「预览」查看练习纸效果，确认后再生成。</p>
    </div>

    <!-- HTML 直出：iframe srcdoc 安全隔离（sandbox 无脚本无同源） -->
    <iframe
      v-else-if="html && !preview"
      class="h-[70vh] w-full rounded-lg border border-stone-300 bg-white dark:border-stone-700"
      sandbox=""
      title="练习纸预览（HTML）"
      :srcdoc="html"
    ></iframe>

    <!-- DTO 渲染 -->
    <div v-else-if="preview" class="space-y-3">
      <div v-if="preview.sections.length === 0" class="panel px-6 py-10 text-center text-sm text-stone-400">
        预览为空 —— 当前筛选（词数 / 来源）没有可用的词。
      </div>
      <div
        v-else
        class="sheet-paper mx-auto w-full max-w-3xl overflow-hidden rounded-md bg-white p-6 text-stone-900 shadow-sm ring-1 ring-stone-200"
        :class="paperClass()"
      >
        <header class="border-b border-stone-300 pb-2 text-center">
          <h3 class="text-base font-bold tracking-wide">DAILY VOCABULARY SHEET</h3>
          <p class="mt-0.5 text-[11px] text-stone-500">
            Lexiora · {{ preview.config.template === 'compact' ? 'Compact' : 'Test' }} ·
            {{ preview.config.paper_size.toUpperCase() }} · {{ preview.config.columns }} 栏 ·
            {{ preview.config.review_count }} 复习 + {{ preview.config.new_count }} 新词
          </p>
        </header>
        <div :class="preview.config.columns === 2 ? 'columns-2 gap-6' : 'columns-1'">
          <div v-for="section in preview.sections" :key="section.kind" class="mb-4 break-inside-avoid">
            <p class="mb-1.5 border-b border-dotted border-stone-400 pb-0.5 text-[11px] font-semibold tracking-widest text-stone-500 uppercase">
              {{ section.kind === 'review' ? '复习 · Review' : '新词 · New' }}
            </p>
            <ol class="space-y-2.5">
              <li v-for="(w, i) in section.words" :key="`${w.lemma}-${i}`" class="break-inside-avoid">
                <p class="flex items-baseline gap-1.5">
                  <span class="w-4 shrink-0 text-right font-mono text-[10px] text-stone-400">{{ i + 1 }}</span>
                  <span class="text-sm font-semibold">{{ w.lemma }}</span>
                  <span v-if="w.personal_phonetic" class="font-mono text-[10px] text-stone-400">/{{ w.personal_phonetic }}/</span>
                  <span v-if="w.part_of_speech" class="ml-auto shrink-0 font-mono text-[10px] text-violet-600 italic">{{ w.part_of_speech }}</span>
                </p>
                <p v-if="preview.config.template === 'compact' && (w.definition_zh || w.definition_en)" class="ml-6 text-[11px] leading-snug text-stone-600">
                  {{ w.definition_zh }}
                  <span v-if="w.definition_zh && w.definition_en" class="mx-0.5 text-stone-300">·</span>
                  <span class="text-stone-500 italic">{{ w.definition_en }}</span>
                </p>
                <p v-else-if="preview.config.template === 'test'" class="ml-6 mt-1 h-5 border-b border-dotted border-stone-300" />
              </li>
            </ol>
          </div>
        </div>
      </div>
      <p class="text-xs text-stone-400">共 {{ preview.word_total }} 个词 · 打印时以实际纸张为准</p>
    </div>

    <p v-if="!hasContent" class="sr-only">练习纸暂无内容</p>
  </div>
</template>

<style scoped>
.sheet-paper {
  font-family: var(--font-sans);
}
</style>
