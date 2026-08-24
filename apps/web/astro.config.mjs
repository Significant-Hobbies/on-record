import cloudflare from '@astrojs/cloudflare';
import { defineConfig } from 'astro/config';

export default defineConfig({
  adapter: cloudflare({ imageService: 'compile' }),
  output: 'server',
  site: 'https://podcasts.highsignal.app',
  server: { host: '127.0.0.1', port: 4321 },
  session: { driver: 'memory' },
});
