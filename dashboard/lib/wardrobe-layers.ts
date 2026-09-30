export const WARDROBE_COARSE_SLOT_MAP: Record<string, string> = {
  upper_body: 'upper_main',
  outerwear: 'upper_outer',
  lower_body: 'lower_main',
  dress: 'onepiece',
  shoes: 'shoes',
  bag: 'bag',
  accessories: 'accessory_1',
};

export function normalizeWardrobeLayer(value: unknown): string {
  const raw = String(value || '').trim();
  return WARDROBE_COARSE_SLOT_MAP[raw] || raw;
}
