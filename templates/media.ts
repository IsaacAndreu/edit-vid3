import { staticFile } from 'remotion';

const REMOTE_URL_PATTERN = /^(https?:|data:|blob:)/i;

/** Resolve either a remote asset URL or a path copied into Remotion's public/ folder. */
export const resolveMediaUrl = (url: string): string =>
  REMOTE_URL_PATTERN.test(url) ? url : staticFile(url);
