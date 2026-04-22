export const USER_TAG_GROUPS = [
  {
    id: "sound-traits",
    label: "Sound Traits",
    tags: [
      { id: "atmospheric", label: "Atmospheric" },
      { id: "punchy", label: "Punchy" },
      { id: "lush", label: "Lush" },
      { id: "raw", label: "Raw" },
      { id: "hazy", label: "Hazy" },
      { id: "sleek", label: "Sleek" },
      { id: "layered", label: "Layered" },
      { id: "groove-heavy", label: "Groove-heavy" },
      { id: "sparse", label: "Sparse" },
      { id: "noisy", label: "Noisy" },
    ],
  },
  {
    id: "emotional-tone",
    label: "Emotional Tone",
    tags: [
      { id: "melancholic", label: "Melancholic" },
      { id: "nostalgic", label: "Nostalgic" },
      { id: "euphoric", label: "Euphoric" },
      { id: "tense", label: "Tense" },
      { id: "reflective", label: "Reflective" },
      { id: "bittersweet", label: "Bittersweet" },
      { id: "playful", label: "Playful" },
      { id: "romantic", label: "Romantic" },
      { id: "defiant", label: "Defiant" },
      { id: "lonely", label: "Lonely" },
      { id: "hopeful", label: "Hopeful" },
    ],
  },
  {
    id: "album-qualities",
    label: "Album Qualities",
    tags: [
      { id: "cohesive", label: "Cohesive" },
      { id: "addictive", label: "Addictive" },
      { id: "ambitious", label: "Ambitious" },
      { id: "polished", label: "Polished" },
      { id: "experimental", label: "Experimental" },
      { id: "accessible", label: "Accessible" },
      { id: "rewarding", label: "Rewarding" },
      { id: "timeless", label: "Timeless" },
      { id: "uneven", label: "Uneven" },
      { id: "distinctive", label: "Distinctive" },
    ],
  },
];

const USER_TAG_LABELS = Object.fromEntries(
  USER_TAG_GROUPS.flatMap((group) => group.tags.map((tag) => [tag.id, tag.label]))
);

export function getUserTagLabel(tagId) {
  return USER_TAG_LABELS[tagId] || tagId;
}
