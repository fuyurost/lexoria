# 从 OpenAPI 再生成客户端（可选，非必需）

`@lexoria/api-client` 是手写的薄 typed client，**不依赖后端当前是否存在**。
当后端提供 OpenAPI 文档后，可以据此（重新）生成一份“跟随文档原样”的 typed
client，而保留共享运行时（single-flight refresh、HttpOnly cookie 会话、统一
错误归一化）不变。

## 工作流

```bash
# 1. 导出后端 OpenAPI 文档（FastAPI 默认在 /openapi.json）
curl -fsSL http://127.0.0.1:8000/openapi.json -o packages/api-client/openapi/schema.json

# 2. 生成 typed client
pnpm generate:openapi
# 或: node packages/api-client/openapi/generate.ts [schema.json] [out.ts]

# 3. 产出文件
#    packages/api-client/openapi/generated-client.ts
```

生成器零依赖（仅 Node），支持 OpenAPI 3.x 常见子集：

- `components/schemas`：object → `interface`；enum → 字面量联合；array /
  anyOf / oneOf / allOf / `$ref`；`nullable` 与 `["string","null"]`；
  `format: date-time` → `IsoDateTime`；内联嵌套对象。
- `paths`：为每个 operation 生成一个 typed wrapper（函数名取
  `operationId`，缺失时回退为 `method_path`），自动处理路径参数插值
  （`encodeURIComponent`）、query 参数对象、requestBody 与 2xx 响应类型；
  `application/pdf` 响应自动按 `Blob` + `responseType: 'blob'` 处理。
- 生成文件内的每个 wrapper 调用共享运行时 `apiRequest(...)`
  （`src/client.ts` 导出），因此刷新/错误语义与手写 client 完全一致。

## 生成的 client 与手写 client 的区别

| | 手写 `src/endpoints.ts` | 生成 `openapi/generated-client.ts` |
|---|---|---|
| 响应解析 | 容错归一化（`normalize.ts`），字段缺失有安全默认值 | 严格按文档 schema |
| 401 刷新 | 共享 | 共享（同一 `apiRequest`） |
| 维护 | 在 v0.1 契约稳定期使用 | 契约稳定后建议切换 |

切换方式：在 `apps/web` 中把 `api` 实例的调用从
`import { api } from '@/lib/api'` 改为引用生成文件中的函数；类型即文档，改动
集中在 `apps/web/src/lib/api.ts` 一层。

## 生成器自身测试

`packages/api-client/src/__tests__/codegen.spec.ts` 用一份 fixture schema 验证
生成产物包含预期的类型与 wrapper（对象、枚举、nullable、$ref、路径参数、
Blob 响应）。生成器默认不做任何网络请求——schema 由你手动导出。
