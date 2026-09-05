# @lexoria/api-client

Lexiora API 的**手写薄 typed client**（Vue 前端共享的唯一契约层）。零运行时
依赖；`apps/web` 通过 pnpm workspace 直接消费本包构建产物。

## 设计约定

- **Access token 仅存内存**（`memoryTokenStore`）；会话持久化依赖 HttpOnly
  refresh cookie，前端 JS 永远看不到它。
- 所有请求带 `credentials: 'include'`。
- 任意非 auth 请求收到 **401** → 触发**单飞（single-flight）cookie 刷新**
  （并发 401 共享同一次 `POST auth/refresh`）→ 重放原请求一次；刷新失败则
  清 token、调用 `onSessionExpired`、抛 `SessionExpiredError`。
- 统一错误模型 `ApiError { status, code, message, details }`，兼容
  `{error:{code,message,details}}` 与扁平错误 JSON。
- 幂等键 `client_event_id` 用 `newClientEventId()`（UUID v4）生成。

## 领域模型要点（已批准模型，类型即契约）

- **UserWord 与 InboxItem 是同一聚合**：状态只有
  `inbox | active | known | archived`（`WordStatus`）；Inbox 列表行的 `id`
  即 `user_word_id`。**没有**任何 ASSUMED ROUTE：
  - 捕获/新建只 `POST /inbox`；
  - 激活/known/archive 一律 `PATCH /user-words/:id { status }`。
- `Familiarity = 0..5 | null`（未评估）。
- Word：`lemma / normalized_lemma / word_id / personal_phonetic / note /
  familiarity / status / card / senses / first_seen_at / last_seen_at /
  encounter_count / recent_sources?`（无 source_id/primary source；来源仅可
  通过 encounters 关联）。
- Sense：`part_of_speech / definition_zh / definition_en / sort_order`；
  Create/Patch 同名且至少一个 definition 非空。
- Card：`difficulty / stability_days / due_at / lapse_count / review_count /
  last_review_at / suspended_at / version`（无 SM2 ease/interval/state）。
- Source：`type ∈ school|ielts|cet4|exam|reading|manual|other / name /
  description / archived_at`；PATCH body 可带 `archived: boolean` 由 API 转换。
- Encounter：`user_word_id / surface_text / source_id / type / context / note /
  encountered_at`，append-only，create 必须带 `client_event_id`。
- DailySheet：表无 status/error/review_count/new_count/source_ids；
  Summary 为 `id / sheet_date / timezone_snapshot / template / paper_size /
  columns / created_at`（+ 可选的 `actual_review_count/actual_new_count`）；
  Detail 含 `items` 快照或 `preview`/`html`。配置请求体仍含
  `review_count / new_count / source_ids`。
- Settings 字段固定 `timezone / daily_template / paper_size / columns /
  review_count / new_count`（无 `default_` 前缀）。
- Login 请求字段固定 `identifier + password`（identifier = 用户名或邮箱）。

## 用法

```ts
import { createLexoriaApi } from '@lexoria/api-client';

export const api = createLexoriaApi({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? '/api/v1',
  onSessionExpired: () => sessionBus.dispatch('expired'),
});

const page = await api.words.list({ q: 'abacus', page: 1, page_size: 20 });
const user = await api.me.get();
await api.reviews.submit(cardId, { rating: 'good', client_event_id: newClientEventId(), expected_card_version: 3 });
await api.words.update(wordId, { status: 'active' });   // inbox 激活
await api.encounters.create({ user_word_id: wordId, context: '…', client_event_id: newClientEventId() });
const pdf = await api.dailySheets.pdf(sheetId);          // Blob → 前端 objectURL 下载
```

## 从 OpenAPI 再生成

见 [`openapi/README.md`](./openapi/README.md)。

## 命令

```bash
pnpm --filter @lexoria/api-client build        # tsc → dist
pnpm --filter @lexoria/api-client typecheck    # tsc --noEmit（含测试）
pnpm --filter @lexoria/api-client test         # vitest run（单飞刷新、归一化、codegen）
```
