import type { LocationSuggestion, RoutePlanResponse } from '../types';

const DEFAULT_API_BASE = 'http://localhost:8000/api';

export async function searchLocations(query: string, signal?: AbortSignal): Promise<LocationSuggestion[]> {
  const base = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE;
  const params = new URLSearchParams({ q: query });
  const response = await fetch(`${base.replace(/\/$/, '')}/geocode/?${params}`, { signal });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data?.message || data?.detail || 'Location search failed. Please try again.');
  }
  return data.suggestions as LocationSuggestion[];
}

export async function submitRoutePlan(payload: Record<string, string | number>) {
  const base = import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE;
  const started = performance.now();
  try {
    const response = await fetch(`${base.replace(/\/$/, '')}/route-plan/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data?.message || data?.detail || 'Route planning failed.');
    }
    return (await response.json()) as RoutePlanResponse;
  } finally {
    console.info('route_plan_frontend_timing', {
      response_and_parse_ms: Number((performance.now() - started).toFixed(1)),
    });
  }
}
