import { env } from 'cloudflare:workers';
import type { RuntimeEnv } from './api';

export function runtimeEnv(): RuntimeEnv {
  return env as RuntimeEnv;
}
