import type { IsoDateTime } from '@lexoria/api-client';

/** Local-timezone Chinese date/time formatting. */
export function formatDateTime(iso: IsoDateTime | null | undefined, withSeconds = false): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    ...(withSeconds ? { second: '2-digit' as const } : {}),
  }).format(d);
}

export function formatDate(iso: IsoDateTime | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' }).format(d);
}

export function formatTime(iso: IsoDateTime | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(d);
}

/** Days from today (negative = overdue). Date-boundary local timezone. */
export function dueInDays(iso: IsoDateTime | null | undefined, now: Date = new Date()): number | null {
  if (!iso) return null;
  const due = new Date(iso);
  if (Number.isNaN(due.getTime())) return null;
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const msPerDay = 86_400_000;
  return Math.round((startOf(due) - startOf(now)) / msPerDay);
}

export function dueLabel(iso: IsoDateTime | null | undefined, now: Date = new Date()): string | null {
  if (!iso) return null;
  const days = dueInDays(iso, now);
  if (days === null) return null;
  if (days === 0) return '今天';
  if (days === 1) return '明天';
  if (days === -1) return '昨天';
  if (days < -1) return `${-days} 天前`;
  if (days < 30) return `${days} 天后`;
  return formatDate(iso);
}

/** '刚刚' / 'N分钟前' / 'N小时前' / date — compact relative timestamps. */
export function relativeTime(iso: IsoDateTime | null | undefined, now: Date = new Date()): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '—';
  const diffMs = now.getTime() - t;
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days === 1) return '昨天';
  if (days < 7) return `${days} 天前`;
  return formatDate(iso);
}

export function timezoneOptions(): string[] {
  const supported = (Intl as unknown as { supportedValuesOf?: (k: string) => string[] }).supportedValuesOf;
  if (typeof supported === 'function') {
    try {
      const zones = supported('timeZone');
      if (zones.length) return [...zones].sort();
    } catch {
      /* fall through to the manual list */
    }
  }
  return [
    'UTC',
    'Asia/Shanghai',
    'Asia/Tokyo',
    'Asia/Singapore',
    'Asia/Seoul',
    'Europe/London',
    'Europe/Paris',
    'Europe/Berlin',
    'America/New_York',
    'America/Los_Angeles',
    'America/Chicago',
    'America/Sao_Paulo',
    'Australia/Sydney',
    'Pacific/Auckland',
  ];
}
