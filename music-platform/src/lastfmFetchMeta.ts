/** Usernames that have completed at least one successful “Fetch my data” (used for auto-refresh on login). */
export const LASTFM_USERNAMES_FETCHED_KEY = "lastfmUsernamesFetchedOnce";

export function readFetchedLastfmUsernames(): Set<string> {
  try {
    const raw = localStorage.getItem(LASTFM_USERNAMES_FETCHED_KEY);
    const arr = raw ? (JSON.parse(raw) as unknown) : [];
    if (!Array.isArray(arr)) return new Set();
    return new Set(arr.map((s) => String(s).trim().toLowerCase()).filter(Boolean));
  } catch {
    return new Set();
  }
}

export function recordLastfmUsernameFetched(username: string): void {
  const s = readFetchedLastfmUsernames();
  s.add(username.trim().toLowerCase());
  localStorage.setItem(LASTFM_USERNAMES_FETCHED_KEY, JSON.stringify([...s]));
}

export function hasFetchedLastfmUsernameBefore(username: string): boolean {
  return readFetchedLastfmUsernames().has(username.trim().toLowerCase());
}

const pipelineTsKey = (username: string) =>
  `lastfmPipelineSuccessAt:${username.trim().toLowerCase()}`;

/** Call after a successful full pipeline run. */
export function recordPipelineSuccessAt(username: string): void {
  try {
    localStorage.setItem(pipelineTsKey(username), new Date().toISOString());
  } catch {
    /* ignore quota */
  }
}

export function getPipelineSuccessAt(username: string): Date | null {
  try {
    const v = localStorage.getItem(pipelineTsKey(username));
    if (!v) return null;
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
}

/** True if a successful run happened within maxAgeMs (used to skip redundant fetches). */
export function pipelineSuccessIsFresh(username: string, maxAgeMs: number): boolean {
  const d = getPipelineSuccessAt(username);
  if (!d) return false;
  return Date.now() - d.getTime() < maxAgeMs;
}
