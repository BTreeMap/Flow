/**
 * useTimezone — reports the user's IANA timezone to the backend.
 *
 * Runs once on mount, rate-limited: sends only if the timezone changed
 * or the last report was more than 6 hours ago. Uses localStorage to
 * persist last-sent state.
 */

import { useEffect } from 'react';
import api from '../api/client';

const STORAGE_KEY = 'flow_tz_last_report';
const SIX_HOURS_MS = 6 * 60 * 60 * 1000;

interface TzReportState {
  timezone: string;
  offset_minutes: number;
  ts: number;
}

export function useTimezone() {
  useEffect(() => {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const offset_minutes = -new Date().getTimezoneOffset();

    // Check rate limit
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const prev: TzReportState = JSON.parse(stored);
        const sameTimezone = prev.timezone === timezone;
        const withinWindow = Date.now() - prev.ts < SIX_HOURS_MS;
        if (sameTimezone && withinWindow) return;
      }
    } catch {
      // Corrupted storage — proceed with report
    }

    // Fire and forget
    api
      .POST('/me/timezone', {
        body: { timezone, offset_minutes },
      })
      .then(() => {
        const state: TzReportState = { timezone, offset_minutes, ts: Date.now() };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
      })
      .catch(() => {
        // Silently ignore — will retry on next page load
      });
  }, []);
}
