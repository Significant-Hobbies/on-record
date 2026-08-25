export function formatClock(seconds?: number | null): string | null {
  if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) {
    return null;
  }
  const total = Math.max(0, Math.floor(Number(seconds)));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
  }
  return `${minutes}:${String(rest).padStart(2, '0')}`;
}

export function formatSaidOn(iso?: string | null): string | null {
  if (!iso) {
    return null;
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toLocaleDateString('en-GB', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

export function whenLabel(input: { saidOn?: string | null; timestampS?: number | null }): string {
  return [formatSaidOn(input.saidOn), formatClock(input.timestampS)].filter(Boolean).join(' · ');
}
