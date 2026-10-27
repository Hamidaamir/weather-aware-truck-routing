import { afterEach, describe, expect, it, vi } from 'vitest';
import { searchLocations } from './client';

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('API base URL configuration', () => {
  it('uses the localhost fallback in development', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '');
    vi.stubEnv('DEV', true);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ suggestions: [] }),
    }));

    await searchLocations('Dallas');

    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/geocode/?q=Dallas',
      { signal: undefined },
    );
  });

  it('uses the configured base URL in production', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.com/api');
    vi.stubEnv('DEV', false);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ suggestions: [] }),
    }));

    await searchLocations('Dallas');

    expect(fetch).toHaveBeenCalledWith(
      'https://api.example.com/api/geocode/?q=Dallas',
      { signal: undefined },
    );
  });

  it('fails clearly when a production API base URL is missing', async () => {
    vi.stubEnv('VITE_API_BASE_URL', '');
    vi.stubEnv('DEV', false);

    await expect(searchLocations('Dallas')).rejects.toThrow(
      'VITE_API_BASE_URL must be configured for production.',
    );
  });
});
