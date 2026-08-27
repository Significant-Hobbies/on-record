import type { APIRoute } from 'astro';

export const GET: APIRoute = () =>
  new Response(null, {
    status: 307,
    headers: { Location: '/api-ai.json' },
  });
