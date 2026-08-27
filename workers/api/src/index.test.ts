import { describe, expect, it } from 'vitest';
import app from './index';

describe('API fallbacks', () => {
  it('returns an agent-readable JSON 404', async () => {
    const response = await app.request('/api/does-not-exist');

    expect(response.status).toBe(404);
    expect(response.headers.get('content-type')).toContain('application/json');
    await expect(response.json()).resolves.toMatchObject({
      error: 'not_found',
      message: expect.any(String),
      resolution: expect.stringContaining('openapi.json'),
    });
  });
});
