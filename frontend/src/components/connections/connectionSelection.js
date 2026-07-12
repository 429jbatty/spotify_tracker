export function resolveEffectiveSelectedId({
  currentSelectionScope,
  focusNodeId,
  nodeIds,
  selectedId,
  selectedSelectionScope,
}) {
  const ids = new Set(nodeIds || []);
  if (
    selectedId
    && selectedSelectionScope === currentSelectionScope
    && ids.has(selectedId)
  ) {
    return selectedId;
  }
  if (focusNodeId) return ids.has(focusNodeId) ? focusNodeId : null;
  return null;
}
