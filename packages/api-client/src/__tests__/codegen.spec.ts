import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { generateTypesFromSchema } from '../../openapi/generate';

const FIXTURE = {
  openapi: '3.1.0',
  info: { title: 'Lexiora fixture', version: '0.1.0' },
  components: {
    schemas: {
      User: {
        type: 'object',
        required: ['id', 'username', 'email', 'created_at'],
        properties: {
          id: { type: 'string', format: 'uuid' },
          username: { type: 'string' },
          email: { type: 'string', format: 'email' },
          created_at: { type: 'string', format: 'date-time' },
        },
      },
      WordStatus: { type: 'string', enum: ['new', 'learning', 'known', 'archived'] },
      CardInfo: {
        type: 'object',
        required: ['id', 'state', 'version'],
        properties: {
          id: { type: 'string' },
          state: { type: 'string', enum: ['new', 'learning', 'review', 'relearning'] },
          due: { type: ['string', 'null'], format: 'date-time' },
          version: { type: 'integer' },
        },
      },
      UserWord: {
        type: 'object',
        required: ['id', 'lemma', 'status', 'senses'],
        properties: {
          id: { type: 'string' },
          lemma: { type: 'string' },
          status: { $ref: '#/components/schemas/WordStatus' },
          card: { $ref: '#/components/schemas/CardInfo' },
          senses: { type: 'array', items: { type: 'object', properties: { definition: { type: 'string' } } } },
          extra: { anyOf: [{ $ref: '#/components/schemas/CardInfo' }, { type: 'null' }] },
        },
      },
    },
  },
  paths: {
    '/user-words': {
      get: {
        operationId: 'listUserWords',
        summary: '分页词库',
        parameters: [
          { name: 'q', in: 'query', schema: { type: 'string' } },
          { name: 'status', in: 'query', schema: { $ref: '#/components/schemas/WordStatus' } },
          { name: 'page', in: 'query', schema: { type: 'integer' } },
        ],
        responses: {
          200: {
            description: 'ok',
            content: { 'application/json': { schema: { type: 'array', items: { $ref: '#/components/schemas/UserWord' } } } },
          },
        },
      },
    },
    '/user-words/{id}': {
      patch: {
        operationId: 'patchUserWord',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        requestBody: {
          required: true,
          content: { 'application/json': { schema: { $ref: '#/components/schemas/UserWord' } } },
        },
        responses: { 200: { description: 'ok', content: { 'application/json': { schema: { $ref: '#/components/schemas/UserWord' } } } } },
      },
    },
    '/daily-sheets/{id}/pdf': {
      get: {
        operationId: 'getDailySheetPdf',
        parameters: [{ name: 'id', in: 'path', required: true, schema: { type: 'string' } }],
        responses: { 200: { description: 'pdf', content: { 'application/pdf': { schema: { type: 'string', format: 'binary' } } } } },
      },
    },
  },
};

describe('openapi codegen', () => {
  const dirs: string[] = [];
  afterEach(() => {
    for (const d of dirs) rmSync(d, { recursive: true, force: true });
  });

  function generate(): string {
    const dir = mkdtempSync(join(tmpdir(), 'lexoria-codegen-'));
    dirs.push(dir);
    const out = join(dir, 'generated-client.ts');
    generateTypesFromSchema(FIXTURE as never, out);
    return readFileSync(out, 'utf8');
  }

  it('emits components as interfaces and enums', () => {
    const src = generate();
    expect(src).toContain('export interface User {');
    expect(src).toContain('created_at: IsoDateTime;');
    expect(src).toContain("export type WordStatus = 'new' | 'learning' | 'known' | 'archived';");
    expect(src).toContain('due?: IsoDateTime | null;');
    // Nullable anyOf collapses to a plain nullable ref.
    expect(src).toContain('extra?: (CardInfo) | null;');
  });

  it('emits per-operation wrappers with typed params and path interpolation', () => {
    const src = generate();
    expect(src).toContain('export interface listUserWordsParams {');
    expect(src).toContain('export function listUserWords(p: listUserWordsParams = {}): Promise<Array<UserWord>> {');
    expect(src).toContain("query: p.query");
    expect(src).toContain('path: `/user-words/${encodeURIComponent(p.path.id)}`');
    expect(src).toContain('body: p.body');
  });

  it('turns pdf responses into blob downloads', () => {
    const src = generate();
    expect(src).toContain('export function getDailySheetPdf(p: getDailySheetPdfParams = {}): Promise<Blob> {');
    expect(src).toContain('export interface getDailySheetPdfParams {');
    expect(src).toContain('id: string;');
    expect(src).toContain("responseType: 'blob'");
  });

  it('prefixes operation function names that collide with reserved words', () => {
    const withCollision = JSON.parse(JSON.stringify(FIXTURE)) as Record<string, unknown>;
    const paths = withCollision.paths as Record<string, { get?: { operationId: string } }>;
    paths['/me'] = { get: { operationId: 'string' } };
    const dir = mkdtempSync(join(tmpdir(), 'lexoria-codegen-'));
    dirs.push(dir);
    const out = join(dir, 'generated-client.ts');
    generateTypesFromSchema(withCollision as never, out);
    const src = readFileSync(out, 'utf8');
    expect(src).toContain('export function string_(');
  });
});
