const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** Format "2026-02-13" → "13 Feb 2026" */
export function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${parseInt(day)} ${MONTHS[parseInt(month) - 1]} ${year}`;
}

/** Format "2026-02-13" → "Feb 2026" (short, for timeline ends) */
export function formatDateShort(iso: string): string {
  const [year, month] = iso.split("-");
  return `${MONTHS[parseInt(month) - 1]} ${year}`;
}
