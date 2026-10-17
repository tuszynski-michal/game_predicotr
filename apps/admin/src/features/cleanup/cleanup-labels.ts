const retainedHistoryLabels: Readonly<Record<string, string>> = {
  grid_reinference_history_preserved: 'Zachowane wyniki ponownego rozpoznania',
  grid_reinference_links_detached: 'Zdjęcia odłączane od zachowanych wyników',
};

export function cleanupCountLabel(name: string): string {
  return retainedHistoryLabels[name] ?? name;
}
