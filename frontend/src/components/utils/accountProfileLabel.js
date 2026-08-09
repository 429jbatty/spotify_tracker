export function accountProfileLabel(account) {
  const profiles = account?.profiles || [];
  if (profiles.length === 1) return profiles[0].display_name;
  if (profiles.length > 1) return `${profiles.length} profiles`;
  return "your account";
}
