import { useEffect, useState } from 'react';

/** Current time that re-renders every `everyMs` (render stays pure: no Date.now() in JSX). */
export function useNow(everyMs = 10_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(id);
  }, [everyMs]);
  return now;
}
