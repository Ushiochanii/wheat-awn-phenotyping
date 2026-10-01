export const SETTINGS_STORAGE_KEY='awn-studio-settings-v1';

export const RESULT_LAYERS=Object.freeze(['edits','representatives','candidates','raw']);
export const WORKSPACE_MODES=Object.freeze(['measure','inspect']);

export const DEFAULT_SETTINGS=Object.freeze({
  autoResolutionAdjustment:true,
  autoGridCalibration:true,
  calibrationPlausibilityCheck:true,
  openCalibrationAfterImport:false,

  defaultModelId:'',
  runAfterCalibration:false,
  continueBatchAfterError:true,
  showLiveInferencePreview:true,
  showCompletionAnimation:true,

  defaultResultLayer:'edits',
  defaultWorkspaceMode:'measure',
  showRelatedCandidates:false,
  showSpikeletContext:true,
  autoFocusSelection:true,
  confirmDestructiveEdits:false,

  rememberPanelLayout:true,
  cacheImagesInMemory:false,

  restoreLastProject:true,
  confirmProjectReplace:true,

  showDiagnostics:true,
});

export function normalizeSettings(value={}){
  const requestedLayer=String(value?.defaultResultLayer??DEFAULT_SETTINGS.defaultResultLayer);
  const requestedMode=String(value?.defaultWorkspaceMode??DEFAULT_SETTINGS.defaultWorkspaceMode);
  return {
    ...DEFAULT_SETTINGS,
    autoResolutionAdjustment:value?.autoResolutionAdjustment!==false,
    autoGridCalibration:value?.autoGridCalibration!==false,
    calibrationPlausibilityCheck:value?.calibrationPlausibilityCheck!==false,
    openCalibrationAfterImport:value?.openCalibrationAfterImport===true,

    defaultModelId:typeof value?.defaultModelId==='string'?value.defaultModelId:'',
    runAfterCalibration:value?.runAfterCalibration===true,
    continueBatchAfterError:value?.continueBatchAfterError!==false,
    showLiveInferencePreview:value?.showLiveInferencePreview!==false,
    showCompletionAnimation:value?.showCompletionAnimation!==false,

    defaultResultLayer:RESULT_LAYERS.includes(requestedLayer)?requestedLayer:DEFAULT_SETTINGS.defaultResultLayer,
    defaultWorkspaceMode:WORKSPACE_MODES.includes(requestedMode)?requestedMode:DEFAULT_SETTINGS.defaultWorkspaceMode,
    showRelatedCandidates:value?.showRelatedCandidates===true,
    showSpikeletContext:value?.showSpikeletContext!==false,
    autoFocusSelection:value?.autoFocusSelection!==false,
    confirmDestructiveEdits:value?.confirmDestructiveEdits===true,

    rememberPanelLayout:value?.rememberPanelLayout!==false,
    cacheImagesInMemory:value?.cacheImagesInMemory===true,

    restoreLastProject:value?.restoreLastProject!==false,
    confirmProjectReplace:value?.confirmProjectReplace!==false,

    showDiagnostics:value?.showDiagnostics!==false,
  };
}

export function loadSettings(storage=globalThis.localStorage){
  try{
    const raw=storage?.getItem?.(SETTINGS_STORAGE_KEY);
    return raw?normalizeSettings(JSON.parse(raw)):normalizeSettings();
  }catch{
    return normalizeSettings();
  }
}

export function saveSettings(settings,storage=globalThis.localStorage){
  const normalized=normalizeSettings(settings);
  try{
    storage?.setItem?.(SETTINGS_STORAGE_KEY,JSON.stringify(normalized));
  }catch{}
  return normalized;
}
