/**
 * normalizeRoomCode — Accepts variants like "bfm-xjg979", "BFMXJG979",
 * "xjg979", " BFM XJG-979 " → "BFM-XJG979".
 * Mirrors backend `normalize_room_code`.
 */
export function normalizeRoomCode(raw: string): string {
  let s = (raw || '').trim().toUpperCase().replace(/[^A-Z0-9\-]/g, '');
  s = s.replace(/^BFM-?/, '');
  s = s.replace(/-/g, '');
  return s ? `BFM-${s}` : '';
}

export function isValidRoomCode(code: string): boolean {
  return /^BFM-[A-Z0-9]{4,12}$/.test(code);
}
