import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Runs an async fetcher and tracks loading/error/data.
 *
 * Deliberately has no "fall back to sample data" behaviour: on failure it
 * reports the error so the UI can say so, rather than showing numbers that
 * were never real.
 */
export function useApi(fetchFn, deps = []) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Keep the latest fetcher without making it a dependency, so callers can
  // pass an inline arrow function without causing a refetch every render.
  const fetchRef = useRef(fetchFn);
  fetchRef.current = fetchFn;

  // Ignore results from requests superseded by a newer one (or by unmount).
  const requestId = useRef(0);

  const refetch = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const result = await fetchRef.current();
      if (id === requestId.current) setData(result);
    } catch (err) {
      if (id === requestId.current) {
        setError(err.message || 'Something went wrong');
        setData(null);
      }
    } finally {
      if (id === requestId.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    refetch();
    return () => {
      // Invalidate in-flight requests on unmount.
      requestId.current++;
    };
  }, [refetch]);

  return { data, loading, error, refetch, setData };
}

/** Debounce a rapidly-changing value, e.g. a search box, before querying. */
export function useDebounced(value, delay = 350) {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
