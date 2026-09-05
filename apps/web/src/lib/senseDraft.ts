/** Sense draft shared by the word detail & inbox activation forms. */
export interface SenseDraft {
  part_of_speech: string;
  definition_zh: string;
  definition_en: string;
}

export const emptySenseDraft = (): SenseDraft => ({
  part_of_speech: '',
  definition_zh: '',
  definition_en: '',
});

/** At least one of the two definitions must be non-empty. */
export function hasDefinition(d: SenseDraft): boolean {
  return d.definition_zh.trim().length > 0 || d.definition_en.trim().length > 0;
}

export const POS_SUGGESTIONS = ['n.', 'v.', 'adj.', 'adv.', 'prep.', 'pron.', 'conj.', 'interj.', 'phrase', 'idiom'];
