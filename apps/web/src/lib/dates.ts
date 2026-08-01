// Formatting for DATE-ONLY database values ("2026-08-01" — Postgres `date`
// columns: night_date, check_in/check_out, event start_date...).
//
// `new Date("2026-08-01")` is parsed as UTC midnight, but toLocaleDateString /
// getDate() then render it in the BROWSER's timezone — a viewer west of UTC
// (e.g. a participant checking from the US) sees the previous day. Same class
// of bug as the hotel check-in shift fixed in 2026-07: render date-only values
// in UTC so the calendar date shown is always the calendar date stored.
//
// Not for real timestamps (flight departure_time, pickup_time...): those are
// moments in time and SHOULD render in the viewer's local timezone.

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/

export function formatDateOnly(
  value: string,
  localeTag: string = 'fr-FR',
  options: Intl.DateTimeFormatOptions = { day: '2-digit', month: '2-digit', year: 'numeric' },
): string {
  const iso = DATE_ONLY.test(value) ? `${value}T00:00:00Z` : value
  const d = new Date(iso)
  if (isNaN(d.getTime())) return value
  return d.toLocaleDateString(localeTag, { ...options, timeZone: 'UTC' })
}
