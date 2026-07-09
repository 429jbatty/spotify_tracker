import { formatRoleLabel } from "./connectionFormatters";

export function connectionRoleLabels(node, connectedNode, links = []) {
  if (!node?.id || !connectedNode?.id) return [];
  const roles = links
    .filter((link) => (
      (link.source === node.id && link.target === connectedNode.id)
      || (link.source === connectedNode.id && link.target === node.id)
    ))
    .map((link) => link.role)
    .filter(Boolean);

  return Array.from(new Set(roles)).map((role) => formatRoleLabel(role));
}
