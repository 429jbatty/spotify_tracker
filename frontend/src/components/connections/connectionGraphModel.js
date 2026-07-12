import { getPrimaryRole } from "./connectionFormatters";

export function buildConnectionGraphModel(graphPayload = {}) {
  const nodes = (graphPayload.nodes || []).map((node) => ({
    ...node,
    name: node.label,
    key: node.type === "album" ? String(node.album_id) : node.person_key,
    primaryRole: getPrimaryRole(node.role_buckets),
  }));
  const links = (graphPayload.edges || []).map((edge) => ({
    ...edge,
    role: edge.role_bucket,
  }));

  return {
    nodes,
    links,
    contributors: nodes.filter((node) => node.type === "contributor"),
    albums: nodes.filter((node) => node.type === "album"),
  };
}

export function relatedIds(selectedId, links) {
  if (!selectedId) return new Set();
  const ids = new Set([selectedId]);
  links.forEach((link) => {
    if (link.source === selectedId) ids.add(link.target);
    if (link.target === selectedId) ids.add(link.source);
  });
  return ids;
}

export function selectedLinks(selectedId, links) {
  if (!selectedId) return links;
  return links.filter((link) => link.source === selectedId || link.target === selectedId);
}

export function previewGraphState({ links, previewNodeId, selectedNodeId }) {
  const previewIds = relatedIds(previewNodeId, links);
  const selectedIds = relatedIds(selectedNodeId, links);
  const previewLinks = previewNodeId ? selectedLinks(previewNodeId, links) : [];
  const selectedLinksForNode = selectedNodeId ? selectedLinks(selectedNodeId, links) : [];

  return {
    emphasizedIds: new Set([...previewIds, ...selectedIds]),
    emphasizedLinks: new Set([...previewLinks, ...selectedLinksForNode]),
    previewIds,
    previewLinks: new Set(previewLinks),
  };
}
