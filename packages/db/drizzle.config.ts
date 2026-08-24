import type { Config } from 'drizzle-kit';

export default {
  dialect: 'sqlite',
  driver: 'd1-http',
  out: './migrations',
  schema: './src/schema.ts',
} satisfies Config;
