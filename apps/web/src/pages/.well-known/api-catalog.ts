import type { APIRoute } from 'astro';

const body = JSON.stringify({
  linkset: [
    {
      anchor: 'https://podcasts.highsignal.app/.well-known/api-catalog',
      item: [
        {
          href: 'https://api.podcasts.highsignal.app',
          title: 'High Signal Podcasts public evidence API',
          type: 'application/json',
        },
      ],
      'service-desc': [
        {
          href: 'https://podcasts.highsignal.app/openapi.json',
          type: 'application/vnd.oai.openapi+json',
        },
      ],
      describedby: [
        {
          href: 'https://podcasts.highsignal.app/developers',
          type: 'text/html',
        },
      ],
    },
  ],
});

const headers = {
  'Cache-Control': 'public, max-age=3600',
  'Content-Type': 'application/linkset+json; profile="https://www.rfc-editor.org/info/rfc9727"',
  Link: '</.well-known/api-catalog>; rel="api-catalog"; type="application/linkset+json"',
};

export const GET: APIRoute = () => new Response(body, { headers });
export const HEAD: APIRoute = () => new Response(null, { headers });
