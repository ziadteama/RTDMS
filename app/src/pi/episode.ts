/** Contract v1.5: optional positive integer; older or malformed values stay unknown. */
export const parseEpisode = (value: unknown): number | null =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= 1 ? value : null;
