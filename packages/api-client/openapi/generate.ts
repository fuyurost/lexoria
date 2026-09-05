/**
 * OpenAPI → typed client generator (zero dependencies).
 *
 * Reads an OpenAPI 3.x document and emits `openapi/generated-client.ts`:
 * one interface/type per schema component plus one wrapper function per
 * operation, all delegating to the package's `apiRequest` runtime so the
 * regenerated client automatically inherits:
 *   - single-flight cookie refresh on 401
 *   - HttpOnly-cookie session semantics (credentials: include)
 *   - unified ApiError normalization
 *   - query serialization / path interpolation
 *
 * Supported schema subset: object/array/primitives/enum/$ref/allOf/anyOf
 * (incl. null unions), nullable, format=date-time, inline objects, JSON and
 * PDF responses. Anything else degrades to `unknown` plus a `// TODO` note so
 * regeneration never silently emits broken calls.
 *
 * CLI:
 *   node openapi/generate.ts [path-to-schema.json]   (default ./openapi/schema.json)
 *   pnpm generate:openapi
 *
 * See openapi/README.md for the full workflow.
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

/* ------------------------------------------------------------------ */
/* small JSON helpers                                                 */
/* ------------------------------------------------------------------ */

type Json = Record<string, unknown>;

function isObj(v: unknown): v is Json {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function str(v: unknown, fb = ''): string {
  return typeof v === 'string' ? v : fb;
}

/* ------------------------------------------------------------------ */
/* schema → TS                                                        */
/* ------------------------------------------------------------------ */

interface Ctx {
  schema: Json;
  /** Full type declarations keyed by (already unique) type name. */
  declarations: Map<string, string>;
  /** Components currently being built — guards allOf/ref cycles. */
  inProgress: Set<string>;
}

function refName(ref: string): string | null {
  const m = /^#\/components\/schemas\/(.+)$/.exec(ref);
  return m ? m[1]!.replace(/\./g, '_') : null;
}

const RESERVED = new Set(['string', 'number', 'boolean', 'object', 'unknown', 'any', 'void', 'Date', 'Record', 'Array', 'null', 'Blob']);

function identName(raw: string): string {
  const cleaned = raw.replace(/[^A-Za-z0-9_$]/g, '_');
  const head = /^[A-Za-z_$]/.test(cleaned) ? cleaned : `T_${cleaned}`;
  return RESERVED.has(head) ? `${head}_` : head;
}

function primitiveType(type: unknown): string | null {
  switch (type) {
    case 'string':
      return 'string';
    case 'integer':
    case 'number':
      return 'number';
    case 'boolean':
      return 'boolean';
    default:
      return null;
  }
}

function enumType(values: unknown[]): string {
  return values
    .map((v) => {
      if (typeof v === 'string') return `'${v.replace(/'/g, "\\'")}'`;
      if (typeof v === 'number' || typeof v === 'boolean') return String(v);
      return 'unknown';
    })
    .join(' | ');
}

function propKey(name: string): string {
  return /^[A-Za-z_$][A-Za-z0-9_$]*$/.test(name) ? name : JSON.stringify(name);
}

/** Inline (anonymous) schema → TS type string. `$ref` only emits the name. */
function inlineType(s: Json, ctx: Ctx, depth: number): string {
  if (depth > 32) return 'unknown';
  if (s.type === 'null') return 'null';
  if (typeof s.$ref === 'string') {
    const name = refName(s.$ref);
    return name ? identName(name) : 'unknown';
  }
  if (Array.isArray(s.anyOf)) return unionType(s.anyOf, ctx, depth);
  if (Array.isArray(s.oneOf)) return unionType(s.oneOf, ctx, depth);
  if (Array.isArray(s.allOf)) return allOfInline(s.allOf, ctx, depth);
  if (Array.isArray(s.enum)) return enumType(s.enum);
  if (Array.isArray(s.type)) {
    // OpenAPI 3.1 style: ["string","null"]
    const hasNull = s.type.includes('null');
    const base = s.type.find((t) => t !== 'null');
    if (base === 'string' && s.format === 'date-time') return hasNull ? 'IsoDateTime | null' : 'IsoDateTime';
    const t = base !== undefined ? primitiveType(base) ?? 'unknown' : 'unknown';
    return hasNull ? `${t} | null` : t;
  }
  if (s.type === 'string' && s.format === 'date-time') return s.nullable === true ? 'IsoDateTime | null' : 'IsoDateTime';
  const base = primitiveType(s.type);
  if (base) return s.nullable === true ? `${base} | null` : base;
  if (s.type === 'array') {
    const item = isObj(s.items) ? inlineType(s.items, ctx, depth + 1) : 'unknown';
    const t = `Array<${item}>`;
    return s.nullable === true ? `${t} | null` : t;
  }
  if (s.type === 'object' || isObj(s.properties)) {
    const t = objectProps(s, ctx, depth);
    return s.nullable === true ? `${t} | null` : t;
  }
  return 'unknown';
}

function objectProps(s: Json, ctx: Ctx, depth: number): string {
  const props = isObj(s.properties) ? s.properties : {};
  const required = Array.isArray(s.required) ? (s.required as string[]) : [];
  if (Object.keys(props).length === 0) return 'Record<string, unknown>';
  const lines: string[] = [];
  for (const [name, raw] of Object.entries(props)) {
    if (!isObj(raw)) continue;
    const t = inlineType(raw, ctx, depth + 1);
    lines.push(`  ${propKey(name)}${required.includes(name) ? '' : '?'}: ${t};`);
  }
  return `{\n${lines.join('\n')}\n}`;
}

function unionType(members: unknown[], ctx: Ctx, depth: number): string {
  const mapped = members.filter(isObj).map((m) => inlineType(m as Json, ctx, depth + 1));
  if (mapped.length === 0) return 'unknown';
  const hasNull = mapped.includes('null');
  const rest = mapped.filter((t) => t !== 'null');
  if (rest.length === 0) return 'unknown';
  const union = rest.length === 1 ? rest[0]! : rest.join(' | ');
  return hasNull ? `(${union}) | null` : union;
}

function allOfInline(members: unknown[], ctx: Ctx, depth: number): string {
  const parts: string[] = [];
  for (const m of members) {
    if (!isObj(m)) continue;
    parts.push(inlineType(m as Json, ctx, depth + 1));
  }
  return parts.length ? parts.join(' & ') : 'unknown';
}

function componentType(name: string, s: Json, ctx: Ctx): void {
  if (ctx.declarations.has(name)) return;
  ctx.inProgress.add(name);
  let body: string;
  if (isObj(s.properties)) {
    body = `export interface ${name} ${objectProps(s, ctx, 0)}`;
  } else if (Array.isArray(s.allOf)) {
    const parts: string[] = [];
    for (const m of s.allOf) {
      if (!isObj(m)) continue;
      if (typeof m.$ref === 'string') {
        const innerRaw = refName(m.$ref);
        if (innerRaw) {
          const inner = identName(innerRaw);
          if (!ctx.declarations.has(inner) && !ctx.inProgress.has(inner)) {
            const target = lookupComponent(ctx.schema, innerRaw);
            if (target) componentType(inner, target, ctx);
          }
          parts.push(inner);
          continue;
        }
      }
      parts.push(inlineType(m as Json, ctx, 1));
    }
    body = `export type ${name} = ${parts.length ? parts.join(' & ') : 'unknown'};`;
  } else if (Array.isArray(s.enum) && s.enum.length > 0) {
    body = `export type ${name} = ${enumType(s.enum)};`;
  } else if (Array.isArray(s.anyOf)) {
    body = `export type ${name} = ${unionType(s.anyOf, ctx, 1)};`;
  } else if (Array.isArray(s.oneOf)) {
    body = `export type ${name} = ${unionType(s.oneOf, ctx, 1)};`;
  } else if (s.type === 'array' || (s.type === undefined && isObj(s.items))) {
    const item = isObj(s.items) ? inlineType(s.items, ctx, 1) : 'unknown';
    body = `export type ${name} = Array<${item}>;`;
  } else {
    body = `export type ${name} = ${inlineType(s, ctx, 0)};`;
  }
  ctx.inProgress.delete(name);
  ctx.declarations.set(name, body);
}

function lookupComponent(schema: Json, rawName: string): Json | null {
  const comps = isObj(schema.components) && isObj(schema.components.schemas) ? schema.components.schemas : {};
  const raw = comps[rawName];
  return isObj(raw) ? raw : null;
}

/* ------------------------------------------------------------------ */
/* operations                                                         */
/* ------------------------------------------------------------------ */

const HTTP_METHODS = ['get', 'post', 'put', 'patch', 'delete'] as const;

interface EmittedOp {
  decls: string[];
  impl: string;
}

function emitOperation(method: string, pathTemplate: string, op: Json, ctx: Ctx): EmittedOp | null {
  const summary = str(op.summary) || str(op.operationId) || `${method.toUpperCase()} ${pathTemplate}`;
  const fallbackId = `${method}_${pathTemplate.replace(/[{}]/g, '_').replace(/[^A-Za-z0-9_]/g, '_')}`;
  const fnName = identName(str(op.operationId) || fallbackId);

  const params = Array.isArray(op.parameters) ? (op.parameters as unknown[]) : [];
  const declaredPathNames: string[] = [];
  const queryNames: string[] = [];
  const pathDeclLines: string[] = [];
  const queryDeclLines: string[] = [];

  for (const rawP of params) {
    const p = isObj(rawP) ? rawP : null;
    if (!p) continue;
    const pName = str(p.name);
    if (!pName) continue;
    const where = str(p.in, 'query');
    const schema = isObj(p.schema) ? (p.schema as Json) : {};
    const t = inlineType(schema, ctx, 1);
    const required = p.required === true;
    const line = `  ${propKey(pName)}${required ? '' : '?'}: ${t};`;
    if (where === 'path') {
      declaredPathNames.push(pName);
      pathDeclLines.push(line);
    } else if (where === 'query') {
      queryNames.push(pName);
      queryDeclLines.push(line);
    }
  }

  // Path placeholders not explicitly declared still need a slot + interpolation.
  for (const m of pathTemplate.matchAll(/\{([^}]+)\}/g)) {
    const name = m[1]!;
    if (!declaredPathNames.includes(name)) {
      declaredPathNames.push(name);
      pathDeclLines.push(`  ${name}: string;`);
    }
  }
  const needsPath = declaredPathNames.length > 0;
  const needsQuery = queryNames.length > 0;

  // Request body.
  let bodyType = 'unknown';
  const rb = op.requestBody;
  const rbRequired = isObj(rb) && rb.required === true;
  if (isObj(rb)) {
    const content = isObj(rb.content) ? rb.content : {};
    const media = isObj(content['application/json']) ? content['application/json'] : null;
    if (media) {
      const schema = isObj(media.schema) ? (media.schema as Json) : media;
      bodyType = inlineType(schema, ctx, 1);
    } else if (content['multipart/form-data'] !== undefined) bodyType = 'FormData';
  }
  const hasBody = bodyType !== 'unknown' || rbRequired;

  // Response: 200 > 201 > 204 > default.
  const responses = isObj(op.responses) ? op.responses : {};
  const picked = isObj(responses['200']) ? responses['200'] : isObj(responses['201']) ? responses['201'] : isObj(responses['204']) ? responses['204'] : responses['default'];
  let responseType = 'void';
  let responseMode = '';
  if (isObj(picked)) {
    const content = isObj(picked.content) ? picked.content : {};
    if (content['application/pdf'] !== undefined) {
      responseType = 'Blob';
      responseMode = ", responseType: 'blob'";
    } else {
      const media = isObj(content['application/json']) ? content['application/json'] : null;
      if (media) {
        const schema = isObj(media.schema) ? (media.schema as Json) : media;
        responseType = inlineType(schema, ctx, 1);
        if (responseType === 'unknown') responseType = 'unknown';
      }
    }
  }

  // Path interpolation: `/user-words/{id}` → `` `/user-words/${encodeURIComponent(p.path.id)}` ``
  const callPath = pathTemplate.includes('{')
    ? '`' + pathTemplate.replace(/[`$\\]/g, '\\$&').replace(/\{([^}]+)\}/g, '${encodeURIComponent(p.path.$1)}') + '`'
    : JSON.stringify(pathTemplate);

  const paramFields: string[] = [];
  if (needsPath) paramFields.push(`path?: {\n${pathDeclLines.join('\n')}\n}`);
  if (needsQuery) paramFields.push(`query?: {\n${queryDeclLines.join('\n')}\n}`);
  if (hasBody) paramFields.push(`body?: ${bodyType};`);

  const paramDecl = paramFields.length
    ? `export interface ${fnName}Params {\n${paramFields.join('\n')}\n}\n`
    : '';

  const callParts: string[] = [`method: '${method.toUpperCase()}'`, `path: ${callPath}`];
  if (needsQuery) callParts.push('query: p.query');
  if (hasBody) callParts.push('body: p.body');
  const opts = callParts.join(', ');
  const paramType = paramFields.length ? `${fnName}Params` : 'Record<string, never>';

  const impl = `/**
 * ${summary}
 * ${method.toUpperCase()} ${pathTemplate}
 */
export function ${fnName}(p: ${paramType} = {}): Promise<${responseType}> {
  return apiRequest<${responseType}>({ ${opts}${responseMode} });
}`;
  return { decls: paramDecl ? [paramDecl] : [], impl };
}

/* ------------------------------------------------------------------ */
/* main                                                                */
/* ------------------------------------------------------------------ */

/** Generates `openapi/generated-client.ts` from an OpenAPI document. */
export function generateTypesFromSchema(schema: Json, outFile: string): string {
  const ctx: Ctx = { schema, declarations: new Map(), inProgress: new Set() };

  const comps = isObj(schema.components) && isObj(schema.components.schemas) ? schema.components.schemas : {};
  for (const [rawName, raw] of Object.entries(comps)) {
    if (!isObj(raw)) continue;
    componentType(identName(rawName), raw as Json, ctx);
  }

  const ops: EmittedOp[] = [];
  const paths = isObj(schema.paths) ? schema.paths : {};
  for (const [pathTemplate, item] of Object.entries(paths)) {
    if (!isObj(item)) continue;
    for (const method of HTTP_METHODS) {
      const op = item[method];
      if (!isObj(op)) continue;
      const emitted = emitOperation(method, pathTemplate, op as Json, ctx);
      if (emitted) ops.push(emitted);
    }
  }

  const header = `/* eslint-disable */
/**
 * AUTO-GENERATED by openapi/generate.ts — DO NOT EDIT BY HAND.
 * Regenerate: pnpm generate:openapi
 *
 * Runtime note: every wrapper delegates to \`apiRequest\`, so the generated
 * client inherits the shared single-flight cookie refresh, HttpOnly-cookie
 * sessions (credentials: include) and unified ApiError normalization from
 * the hand-written client. Wrappers do NOT normalize payloads the way the
 * hand-written client does — they follow the OpenAPI document verbatim.
 */
import { apiRequest } from './client';

export type IsoDateTime = string;
`;

  const declBlock = Array.from(ctx.declarations.values()).join('\n\n');
  const fnBlock = ops.map((o) => `${o.decls.join('\n\n')}\n${o.impl}`).join('\n\n');
  const out = `${header}\n${declBlock}\n\n/* ------------------------------------------------------------------ */\n/* operations                                                          */\n/* ------------------------------------------------------------------ */\n\n${fnBlock}\n`;
  writeFileSync(outFile, out, 'utf8');
  return out;
}

/* ------------------------------------------------------------------ */
/* CLI                                                                 */
/* ------------------------------------------------------------------ */

function main(): void {
  const here = dirname(fileURLToPath(import.meta.url));
  const schemaPath = process.argv[2] ?? join(here, 'schema.json');
  const outFile = process.argv[3] ?? join(here, 'generated-client.ts');
  if (!existsSync(schemaPath)) {
    console.error(`schema 不存在: ${schemaPath}`);
    console.error('先导出后端 OpenAPI 文档，例如:');
    console.error('  curl -fsSL http://127.0.0.1:8000/openapi.json -o packages/api-client/openapi/schema.json');
    console.error('  pnpm generate:openapi');
    process.exitCode = 1;
    return;
  }
  let schema: Json;
  try {
    schema = JSON.parse(readFileSync(schemaPath, 'utf8')) as Json;
  } catch (err) {
    console.error(`无法解析 ${schemaPath}:`, err);
    process.exitCode = 1;
    return;
  }
  const out = generateTypesFromSchema(schema, outFile);
  console.log(`已生成 ${outFile}（${out.length} 字节）`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}
