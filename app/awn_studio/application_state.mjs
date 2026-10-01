export function createApplicationState() {
  const state = {
    workspaceMode: 'measure',
    activeDisplayLayer: 'edits',
    inspectionStep: 0,
    inspectionBranchIndex: 0,
    selectedLayerObject: null,
    reviewFilter: 'all'
  };

  function setWorkspaceMode(mode) {
    if (!['measure', 'inspect'].includes(mode)) {
      throw new Error(`Unsupported workspace mode: ${mode}`);
    }
    state.workspaceMode = mode;
  }

  function setDisplayLayer(layer) {
    if (!['edits', 'raw', 'candidates', 'representatives'].includes(layer)) {
      throw new Error(`Unsupported display layer: ${layer}`);
    }
    state.activeDisplayLayer = layer;
  }

  function setReviewFilter(filter) {
    state.reviewFilter = String(filter || 'all');
  }

  function resetInspection() {
    state.inspectionStep = 0;
    state.inspectionBranchIndex = 0;
    state.selectedLayerObject = null;
  }

  function setInspectionStep(step) {
    state.inspectionStep = Math.max(0, Number(step) || 0);
  }

  function setInspectionBranchIndex(index) {
    state.inspectionBranchIndex = Math.max(0, Number(index) || 0);
  }

  function setSelectedLayerObject(value) {
    state.selectedLayerObject = value ?? null;
  }

  return Object.seal({
    state,
    setWorkspaceMode,
    setDisplayLayer,
    setReviewFilter,
    resetInspection,
    setInspectionStep,
    setInspectionBranchIndex,
    setSelectedLayerObject
  });
}
