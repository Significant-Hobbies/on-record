import { defineMiddleware } from 'astro:middleware';

const agentView = {
  name: 'High Signal Podcasts',
  alternateName: 'On the Record',
  purpose: 'Find and verify source-backed claims and recommendations from notable podcast guests.',
  evidenceContract:
    'Published claims keep the speaker, verbatim excerpt, date, and primary source evidence attached. Missing evidence stays missing.',
  access: {
    auth: 'none',
    mode: 'public-read-only',
    pricing:
      'No account, API key, or checkout is currently required. No permanent pricing model is promised.',
  },
  api: {
    baseUrl: 'https://api.podcasts.highsignal.app',
    openapi: 'https://podcasts.highsignal.app/openapi.json',
  },
  discovery: {
    catalog: 'https://podcasts.highsignal.app/api/ai',
    apiCatalog: 'https://podcasts.highsignal.app/.well-known/api-catalog',
    llms: 'https://podcasts.highsignal.app/llms.txt',
    markdown: 'https://podcasts.highsignal.app/index.md',
    sitemap: 'https://podcasts.highsignal.app/sitemap.xml',
    skill: 'https://podcasts.highsignal.app/.well-known/agent-skills/on-record-evidence/SKILL.md',
  },
  guidance: {
    developers: 'https://podcasts.highsignal.app/developers',
    methodology: 'https://podcasts.highsignal.app/methodology',
    access: 'https://podcasts.highsignal.app/pricing',
    contact: 'https://podcasts.highsignal.app/contact',
  },
};

const markdownRoutes = new Map([
  ['/', '/index.md'],
  ['/people', '/people.md'],
  ['/recommendations', '/recommendations.md'],
  ['/sources', '/sources.md'],
  ['/search', '/search.md'],
  ['/methodology', '/methodology.md'],
  ['/developers', '/developers.md'],
  ['/about', '/about.md'],
  ['/privacy', '/privacy.md'],
  ['/pricing', '/pricing.md'],
  ['/contact', '/contact.md'],
]);

export const onRequest = defineMiddleware(async (context, next) => {
  if (context.url.pathname === '/' && context.url.searchParams.get('mode') === 'agent') {
    return Response.json(agentView, {
      headers: {
        'Cache-Control': 'public, max-age=300',
        Link: [
          '</api/ai>; rel="service-meta"; type="application/json"',
          '</openapi.json>; rel="service-desc"; type="application/vnd.oai.openapi+json"',
          '</.well-known/api-catalog>; rel="api-catalog"; type="application/linkset+json"',
          '</index.md>; rel="alternate"; type="text/markdown"',
        ].join(', '),
      },
    });
  }

  const response = await next();
  const links = [
    '</sitemap.xml>; rel="sitemap"; type="application/xml"',
    '</llms.txt>; rel="describedby"; type="text/plain"',
    '</api/ai>; rel="service-meta"; type="application/json"',
    '</openapi.json>; rel="service-desc"; type="application/vnd.oai.openapi+json"',
    '</.well-known/api-catalog>; rel="api-catalog"; type="application/linkset+json"',
  ];
  const markdown = markdownRoutes.get(context.url.pathname.replace(/\/$/, '') || '/');
  if (markdown) {
    links.push(`<${markdown}>; rel="alternate"; type="text/markdown"`);
  }
  response.headers.set('Link', links.join(', '));
  return response;
});
