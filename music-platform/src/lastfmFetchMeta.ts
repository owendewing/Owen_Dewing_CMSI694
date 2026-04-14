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
