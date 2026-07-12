import { formatRoleSummary } from "./connectionFormatters";

export function filterContributorOptions(contributors, query) {
  const terms = query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);

  return contributors
    .filter((contributor) => {
      if (terms.length === 0) return true;
      const text = [
        contributor.person_name,
        formatRoleSummary(contributor.role_buckets),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return terms.every((term) => text.includes(term));
    })
    .slice(0, 8);
}
