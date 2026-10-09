import cloudflare from '@astrojs/cloudflare';
import { defineConfig } from 'astro/config';

export default defineConfig({
  adapter: cloudflare({ imageService: 'compile' }),
  output: 'server',
  compressHTML: true,
  site: 'https://podcasts.highsignal.app',
  server: { host: '127.0.0.1', port: 4321 },
  session: { driver: 'memory' },
  build: { inlineStylesheets: 'always' },
  vite: {
    // The adapter loads Wrangler vars into process.env; keep build-time API base precedence.
    define: {
      'import.meta.env.PUBLIC_API_BASE': JSON.stringify(process.env.PUBLIC_API_BASE ?? ''),
    },
  },
});
