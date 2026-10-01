import {readingOrder,distance,pathLength,lengthMM,validName,nextName,nearestSegment,simplifyPathDP1,csv,validateProject,zipFiles} from './core.mjs?v=20260928-14';
import {geometryPath,timingLabels} from './layers.mjs?v=20260928-14';
import {applyStaticTranslations,t} from './i18n.mjs?v=20260930-scale1';
import {PROJECT_SCHEMA,normalizeProductResult,editableGroupsFromProductResult,inspectionRecordForSpikelet,displayLayersFromProductResult,timingsFromProductResult,resultSummary} from './contracts.mjs?v=20260929-20';
import {createProjectStore} from './project_store.mjs?v=20260929-10';
import {createInferenceClient} from './inference_client.mjs?v=20260928-14';
import {isMeasurementResultPage,measurementResultModelId,hasMeasurementResult,pendingSourcePages as collectPendingSourcePages,uncalibratedPendingSourcePages,projectPageStatus,navigationPages,navigationTarget,currentMeasurementPage,exportableMeasurementPages,matchingUncalibratedSources,cascadePageIds} from './workflow.mjs?v=20260928-14';
import {detailedProjectCsv} from './export.mjs?v=20260929-20';
import {encodeProject,decodeProject} from './project_codec.mjs?v=20260928-14';
import {createPerformanceMonitor} from './performance_monitor.mjs?v=20260928-14';
import {createRenderScheduler} from './render_scheduler.mjs?v=20260929-10';
import {createPersistenceController} from './persistence_controller.mjs?v=20260929-10';
import {createHistoryManager} from './history_manager.mjs?v=20260928-14';
import {createInteractionController} from './interaction_controller.mjs?v=20260928-14';
import {createApplicationState} from './application_state.mjs?v=20260928-14';
import {buildHydratedProjectSnapshot} from './export_snapshot.mjs?v=20260928-14';
import {renderInspectionOverlay as renderInspectionOverlayLayer,renderEditableAnnotations,updateEditableGeometry,updateEditableNodePosition,updateMarqueeRect} from './canvas_renderers.mjs?v=20260929-21';
import {effectiveReviewStatus,reviewReasonLabels} from './review_triage.mjs?v=20260929-20';
import {confidenceFilteredLine} from './confidence_filter.mjs?v=20260929-24';
import {loadSettings,saveSettings} from './settings.mjs?v=20260930-scale1';

// Promoted from the validated 8782 twin on 2026-09-30. Keep the existing
// feature branches intact for this freeze; the promoted behavior is now the
// official Workbench default rather than a query-string experiment.
const POSTPROCESS_LAB=true;
const resolutionGateModule=import('./resolution_gate.mjs?v=20260930-freeze1');
const experimentCalibrationModule=import('./calibration.mjs?v=20260930-scale1');
const $=id=>document.getElementById(id),svg=$('canvas'),NS='http://www.w3.org/2000/svg',clone=x=>structuredClone(x);
const perf=createPerformanceMonitor();
let appSettings=loadSettings();
applyStaticTranslations();
function syncDiagnosticsVisibility(){
 const provenance=document.querySelector('.inspect-provenance-note');
 if(provenance)provenance.hidden=!appSettings.showDiagnostics;
 document.body.classList.toggle('hide-diagnostics',!appSettings.showDiagnostics);
}
function syncSettingsUI(){
 const values={
  'setting-auto-resolution':appSettings.autoResolutionAdjustment,
  'setting-auto-grid':appSettings.autoGridCalibration,
  'setting-plausibility':appSettings.calibrationPlausibilityCheck,
  'setting-open-calibration':appSettings.openCalibrationAfterImport,
  'setting-run-after-calibration':appSettings.runAfterCalibration,
  'setting-continue-batch':appSettings.continueBatchAfterError,
  'setting-live-preview':appSettings.showLiveInferencePreview,
  'setting-completion-animation':appSettings.showCompletionAnimation,
  'setting-related-candidates':appSettings.showRelatedCandidates,
  'setting-spikelet-context':appSettings.showSpikeletContext,
  'setting-auto-focus':appSettings.autoFocusSelection,
  'setting-confirm-edits':appSettings.confirmDestructiveEdits,
  'setting-remember-layout':appSettings.rememberPanelLayout,
  'setting-cache-images':appSettings.cacheImagesInMemory,
  'setting-restore-project':appSettings.restoreLastProject,
  'setting-confirm-project-replace':appSettings.confirmProjectReplace,
  'setting-show-diagnostics':appSettings.showDiagnostics,
 };
 for(const [id,value] of Object.entries(values)){const node=$(id);if(node)node.checked=value;}
 const model=$('setting-default-model');if(model&&[...model.options].some(option=>option.value===appSettings.defaultModelId))model.value=appSettings.defaultModelId;
 const layer=$('setting-default-layer');if(layer)layer.value=appSettings.defaultResultLayer;
 const workspaceMode=$('setting-default-workspace');if(workspaceMode)workspaceMode.value=appSettings.defaultWorkspaceMode;
 const plausibility=$('setting-plausibility');if(plausibility)plausibility.disabled=!appSettings.autoGridCalibration;
 syncDiagnosticsVisibility();
}
function setSettingsSection(section='input'){
 for(const button of document.querySelectorAll('[data-settings-section]'))button.setAttribute('aria-pressed',String(button.dataset.settingsSection===section));
 for(const panel of document.querySelectorAll('[data-settings-panel]'))panel.hidden=panel.dataset.settingsPanel!==section;
}
function saveAppSetting(key,value){
 appSettings=saveSettings({...appSettings,[key]:value});
 syncSettingsUI();
 if(key==='autoGridCalibration')experimentCalibrationModule.then(module=>module?.setAutoGridEnabled?.(appSettings.autoGridCalibration));
 if(key==='defaultModelId')applyConfiguredDefaultModel();
 if(key==='showRelatedCandidates'){const pool=$('inspect-show-pool');if(pool)pool.checked=appSettings.showRelatedCandidates;drawInspectionOverlay();}
 if(key==='showSpikeletContext')maskRenderKey='';
 if(key==='cacheImagesInMemory'&&!appSettings.cacheImagesInMemory)for(const item of project.pages)if(item.id!==active&&item.assetRef&&item.src)delete item.src;
 if(key==='rememberPanelLayout'&&!appSettings.rememberPanelLayout){
  try{localStorage.removeItem('awn-studio-left-panel');localStorage.removeItem('awn-studio-right-panel');}catch{}
  setPanelWidth('left',panelDefaults.left,false);setPanelWidth('right',panelDefaults.right,false);
 }
 render({panels:true,images:false,canvas:true,tools:false});
}
$('settings-open').onclick=()=>{syncSettingsUI();setSettingsSection(document.querySelector('[data-settings-section][aria-pressed="true"]')?.dataset.settingsSection??'input');$('settings-dialog').showModal();};
for(const button of document.querySelectorAll('[data-settings-section]'))button.onclick=()=>setSettingsSection(button.dataset.settingsSection);
for(const [id,key] of [
 ['setting-auto-resolution','autoResolutionAdjustment'],
 ['setting-auto-grid','autoGridCalibration'],
 ['setting-plausibility','calibrationPlausibilityCheck'],
 ['setting-open-calibration','openCalibrationAfterImport'],
 ['setting-run-after-calibration','runAfterCalibration'],
 ['setting-continue-batch','continueBatchAfterError'],
 ['setting-live-preview','showLiveInferencePreview'],
 ['setting-completion-animation','showCompletionAnimation'],
 ['setting-related-candidates','showRelatedCandidates'],
 ['setting-spikelet-context','showSpikeletContext'],
 ['setting-auto-focus','autoFocusSelection'],
 ['setting-confirm-edits','confirmDestructiveEdits'],
 ['setting-remember-layout','rememberPanelLayout'],
 ['setting-cache-images','cacheImagesInMemory'],
 ['setting-restore-project','restoreLastProject'],
 ['setting-confirm-project-replace','confirmProjectReplace'],
 ['setting-show-diagnostics','showDiagnostics'],
])$(id).onchange=e=>saveAppSetting(key,e.currentTarget.checked);
$('setting-default-model').onchange=e=>saveAppSetting('defaultModelId',e.currentTarget.value);
$('setting-default-layer').onchange=e=>saveAppSetting('defaultResultLayer',e.currentTarget.value);
$('setting-default-workspace').onchange=e=>saveAppSetting('defaultWorkspaceMode',e.currentTarget.value);
experimentCalibrationModule.then(module=>module?.installTwinCalibrationUI({autoGridEnabled:appSettings.autoGridCalibration}));
syncSettingsUI();
// Lucide v0.468.0 icons, ISC license; see THIRD_PARTY_NOTICES.md.
const toolIcon=paths=>`<svg class="tool-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
document.querySelector('[data-tool="select"] span').innerHTML=toolIcon('<path d="M18 11V6a2 2 0 0 0-2-2 2 2 0 0 0-2 2"/><path d="M14 10V4a2 2 0 0 0-2-2 2 2 0 0 0-2 2v2"/><path d="M10 10.5V6a2 2 0 0 0-2-2 2 2 0 0 0-2 2v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>');
document.querySelector('[data-tool="box"] span').innerHTML=toolIcon('<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/>');
$('source-preview-toggle').querySelector('span').innerHTML=toolIcon('<path d="M2.1 12s3.5-6 9.9-6 9.9 6 9.9 6-3.5 6-9.9 6S2.1 12 2.1 12Z"/><circle cx="12" cy="12" r="2.5"/>');
$('canvas-add-spikelet').querySelector('span').innerHTML=toolIcon('<circle cx="12" cy="12" r="8"/><path d="M12 8v8M8 12h8"/>');
$('canvas-redraw-awn').querySelector('span').innerHTML=toolIcon('<path d="m3 17 5-5 4 4 8-9"/><path d="M16 7h4v4"/>');
$('canvas-delete-selection').querySelector('span').innerHTML=toolIcon('<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="m19 6-1 14H6L5 6"/><path d="M10 11v5M14 11v5"/>');
$('canvas-focus-selection').querySelector('span').innerHTML=toolIcon('<circle cx="12" cy="12" r="3"/><path d="M3 8V5a2 2 0 0 1 2-2h3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3"/>');
$('undo').querySelector('span').innerHTML=toolIcon('<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5 5.5 5.5 0 0 1-5.5 5.5H11"/>');
$('redo').querySelector('span').innerHTML=toolIcon('<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5A5.5 5.5 0 0 0 4 14.5 5.5 5.5 0 0 0 9.5 20H13"/>');
document.querySelector('[data-layer="raw"]').firstChild.textContent=t('layers.evidence')+' ';
document.querySelector('[data-layer="candidates"]').firstChild.textContent=t('layers.candidates')+' ';
document.querySelector('[data-layer="representatives"]').firstChild.textContent=t('layers.representatives')+' ';
const viewTools=document.createElement('div');viewTools.id='canvas-view-tools';viewTools.setAttribute('aria-label','Canvas view');viewTools.innerHTML='<button id="fit">Fit</button><button id="zoom-out" aria-label="Zoom out">−</button><span id="zoom-label">100%</span><button id="zoom-in" aria-label="Zoom in">＋</button>';$('canvas-wrap').appendChild(viewTools);
const workspace=$('main')??document.querySelector('main'),panelDefaults={left:158,right:282};
function panelWidth(side){return Number.parseFloat(getComputedStyle(workspace).getPropertyValue(`--${side}-panel`))||panelDefaults[side];}
function panelLimit(side,value){const other=panelWidth(side==='left'?'right':'left'),minimum=side==='left'?120:240,room=Math.max(minimum,workspace.clientWidth-other-432);return Math.round(Math.max(minimum,Math.min(side==='left'?420:500,room,value)));}
function setPanelWidth(side,value,save=true){const width=panelLimit(side,value);workspace.style.setProperty(`--${side}-panel`,`${width}px`);const handle=$(side+'-resizer');handle.setAttribute('aria-valuenow',String(width));handle.setAttribute('aria-valuemin',side==='left'?'120':'240');handle.setAttribute('aria-valuemax',side==='left'?'420':'500');if(save&&appSettings.rememberPanelLayout)try{localStorage.setItem(`awn-studio-${side}-panel`,String(width));}catch{}return width;}
function setupPanelResizer(side){const handle=$(side+'-resizer');let saved;if(appSettings.rememberPanelLayout)try{saved=Number(localStorage.getItem(`awn-studio-${side}-panel`));}catch{}setPanelWidth(side,Number.isFinite(saved)&&saved>0?saved:panelDefaults[side],false);handle.onpointerdown=e=>{if(e.button!==0)return;const start=e.clientX,width=panelWidth(side);handle.classList.add('dragging');handle.setPointerCapture(e.pointerId);handle.onpointermove=move=>setPanelWidth(side,width+(side==='left'?move.clientX-start:start-move.clientX),false);handle.onpointerup=()=>{handle.onpointermove=null;handle.onpointerup=null;handle.classList.remove('dragging');setPanelWidth(side,panelWidth(side));};};handle.ondblclick=()=>setPanelWidth(side,panelDefaults[side]);handle.onkeydown=e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();const direction=e.key==='ArrowRight'?1:-1;setPanelWidth(side,panelWidth(side)+(side==='left'?direction:-direction)*10);};}
setupPanelResizer('left');setupPanelResizer('right');
let selectedKind='polygon';
let sourcePreviewPinned=false;
let inferencePreview=null;
const applicationState=createApplicationState(),uiState=applicationState.state;
let modelAvailable=false,modelCatalog=[],modelCatalogDefaultId=null,modelDevice='0',inferenceRunning=false,batchRunning=false,batchStopRequested=false,pendingCalibrationContinuation=null,inferenceElapsedTimer=null,inferenceElapsedStartedAt=null;
let project={schema:PROJECT_SCHEMA,pages:[]},active=null,selected=null,selectedObjects=[],selectedNodes=[],selectedImages=new Set(),tool='select',draft=[],scaleDraft=null,node=null,marquee=null,view=[0,0,100,100],toastTimer,ready=false;
const interaction=createInteractionController();
const sourcePreviewActive=()=>interaction.ctrl||sourcePreviewPinned;
const DISPLAY_OPACITY=Object.freeze({contextSpikeletFill:.16,contextSpikeletEdge:.55,rawSpikeletFill:.28,rawSpikeletEdge:.72,candidateFill:.82,representativeFill:.90,interactiveLine:1});
function evidenceConfidenceOpacity(item){const confidence=Number(item?.confidence);if(!Number.isFinite(confidence))return .26;const normalized=Math.max(0,Math.min(1,(confidence-.25)/.75));return .08+.34*Math.sqrt(normalized);}
const page=()=>project.pages.find(p=>p.id===active),group=()=>page()?.groups.find(g=>g.uid===selected),uid=()=>globalThis.crypto?.randomUUID?.()??Date.now().toString(36)+Math.random().toString(36).slice(2);
const objectSelected=(id,kind)=>selectedObjects.some(o=>o.uid===id&&o.kind===kind);
const nodeSelected=(id,kind,index)=>selectedNodes.some(n=>n.uid===id&&n.kind===kind&&n.index===index);
function syncCanvasActionButtons(){const editing=uiState.workspaceMode==='measure'&&!!page(),hasGroup=!!group(),hasSelection=selectedObjects.length>0||selectedNodes.length>0||!!node;for(const button of document.querySelectorAll('#canvas-tools [data-editing-only]'))button.disabled=!editing;$('canvas-redraw-awn').disabled=!editing||!hasGroup;$('canvas-delete-selection').disabled=!editing||!hasSelection;$('canvas-focus-selection').disabled=!hasGroup;$('source-preview-toggle').disabled=!page();$('source-preview-toggle').setAttribute('aria-pressed',String(sourcePreviewPinned));}
function clearSelection(){selected=null;selectedObjects=[];selectedNodes=[];node=null;applicationState.resetInspection();}
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4200);}
let downloadURL=null;
function download(blob,name){
 if(downloadURL)URL.revokeObjectURL(downloadURL);
 downloadURL=URL.createObjectURL(blob);const ownURL=downloadURL;
 const link=$('download-link');link.href=downloadURL;link.download=name;
 $('download-name').textContent=name;
 $('download-size').textContent=t('download.readySize',{kb:(blob.size/1024).toFixed(1)});
 $('download-text').hidden=true;$('download-text').value='';
 if(blob.type!=='application/zip'&&blob.size<=2*1024*1024)blob.text().then(text=>{if(downloadURL===ownURL){$('download-text').value=text;$('download-text').hidden=false;}});
 for(const dialog of document.querySelectorAll('dialog[open]'))dialog.close();
 $('download-dialog').showModal();
}
const dataURL=blob=>new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(blob);});
const imageSize=src=>new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>resolve([im.naturalWidth,im.naturalHeight]);im.onerror=()=>reject(Error(t('error.imageDecode')));im.src=src;});
const projectStore=createProjectStore();
const assetLoads=new Map();
async function loadImageAsset(ref){
 if(!ref)return null;
 ref=String(ref);
 let pending=assetLoads.get(ref);
 if(!pending){
  const started=perf.start();
  pending=projectStore.loadAsset(ref).then(source=>{
   if(!source)throw Error(`Stored image asset ${ref} is missing.`);
   perf.end('asset.load',started);
   return source;
  }).finally(()=>assetLoads.delete(ref));
  assetLoads.set(ref,pending);
 }
 return pending;
}
async function ensureImageLoaded(target=page()){
 if(!target||target.src||!target.assetRef)return target?.src??null;
 const source=await loadImageAsset(target.assetRef);
 target.src=source;
 return source;
}
async function ensureStoredImageAsset(target){
 if(!target)return null;
 if(target.assetRef)return String(target.assetRef);
 if(!target.src)return null;
 const ref=String(target.id);
 await projectStore.saveAsset(ref,target.src);
 target.assetRef=ref;
 return ref;
}
async function ensureAllImagesLoaded(pages=project.pages){
 const seen=new Set();
 for(const target of pages){
  if(target?.sourcePageId)continue;
  if(!target?.assetRef||target.src||seen.has(String(target.assetRef)))continue;
  seen.add(String(target.assetRef));
  await ensureImageLoaded(target);
 }
}
const inferenceLoads=new Map();
function hydrateReviewTriage(target,inference){if(!target||!inference||!Array.isArray(target.groups))return false;const projected=editableGroupsFromProductResult(inference),byId=new Map(projected.map(g=>[String(g.uid),g]));let changed=false;for(const g of target.groups){const source=byId.get(String(g.uid));if(!source)continue;const nextStatus=source.autoReviewStatus??'automatic',nextReasons=clone(source.reviewReasons??[]),nextSignals=clone(source.reviewSignals??{});if(g.autoReviewStatus!==nextStatus||JSON.stringify(g.reviewReasons??[])!==JSON.stringify(nextReasons)||JSON.stringify(g.reviewSignals??{})!==JSON.stringify(nextSignals)){g.autoReviewStatus=nextStatus;g.reviewReasons=nextReasons;g.reviewSignals=nextSignals;changed=true;}}return changed;}
async function ensureInferenceLoaded(target=page()){
 if(!target)return null;if(target.inference){hydrateReviewTriage(target,target.inference);return target.inference;}if(!target.inferenceRef)return null;
 const ref=String(target.inferenceRef);
 let pending=inferenceLoads.get(ref);
 if(!pending){
  const started=perf.start();
  pending=projectStore.loadInference(ref).then(stored=>{
   if(!stored)throw Error(`Stored inference result ${ref} is missing.`);
   const normalized=normalizeProductResult(stored);
   target.inference=normalized;
   hydrateReviewTriage(target,normalized);
   applyConfidenceFilterToPage(target,target.confidenceThreshold??0,{clearConfirmed:false});
   perf.end('inference.load',started);
   return normalized;
  }).finally(()=>inferenceLoads.delete(ref));
  inferenceLoads.set(ref,pending);
 }
 return pending;
}
async function ensureAllInferenceLoaded(pages=project.pages){
 for(const target of pages)if(target?.inferenceRef&&!target.inference)await ensureInferenceLoaded(target);
}
const persistence=createPersistenceController({
 store:projectStore,
 getProject:()=>project,
 encodeProject,
 onStatus(status){$('save-status').textContent=status==='saving'?t('status.saving'):status==='saved'?t('status.savedLocal'):t('status.saveFailed');},
 onError(){toast(t('status.localUnavailable'));},
 onMeasure:(name,durationMs)=>perf.record(name,durationMs)
});
function schedulePersist({full=false,pageIds=[active]}={}){persistence.markChanged({full,pageIds});}
function changed({panels=true,structural=false,pageIds=[active]}={}){project.updatedAt=new Date().toISOString();schedulePersist({full:structural,pageIds});if(panels)render({panels:true,images:false,canvas:false,tools:false});}
window.addEventListener('beforeunload',e=>{if(persistence.dirty){e.preventDefault();e.returnValue='';}});
const historyManager=createHistoryManager({limit:70});
const projectSyncChannel=typeof BroadcastChannel==='function'?new BroadcastChannel('awn-studio-project-sync-v1'):null;
function resetProjectToEmpty(){project={schema:PROJECT_SCHEMA,pages:[]};active=null;selectedImages.clear();clearSelection();historyManager.clear();draft=[];scaleDraft=null;tool='select';sourcePreviewPinned=false;view=[0,0,100,100];svg.setAttribute('viewBox',view.join(' '));syncPhoto();render();}
if(projectSyncChannel)projectSyncChannel.onmessage=async event=>{if(event.data?.type!=='project-cleared')return;try{await persistence.discardPending();await projectStore.clearCurrent();resetProjectToEmpty();$('save-status').textContent=t('status.savedLocal');}catch(error){toast(error.message);}};
function snapshot(pageIds=[active]){
 const ids=new Set(pageIds.filter(Boolean));
 return{active,selected,selectedKind,view:[...view],pages:project.pages.filter(p=>ids.has(p.id)).map(p=>({id:p.id,groups:clone(p.groups),calibration:clone(p.calibration)}))};
}
function checkpoint({pageIds=[active]}={}){historyManager.checkpoint(snapshot(pageIds));}
function restore(s){for(const v of s.pages){const p=project.pages.find(p=>p.id===v.id);if(p){p.groups=clone(v.groups);p.calibration=clone(v.calibration);}}active=s.active;clearSelection();selectedKind=s.selectedKind??'polygon';if(s.selected&&groupById(s.selected)){selected=s.selected;selectedObjects=[{uid:selected,kind:selectedKind}];}marquee=null;draft=[];tool='select';syncPhoto();setView(s.view??[0,0,page().width,page().height]);render();changed({pageIds:s.pages.map(v=>v.id)});}
function undo(){return perf.measureAction('undo',()=>{const target=historyManager.peekUndo();if(!target)return;const ids=target.pages.map(p=>p.id);restore(historyManager.undo(snapshot(ids)));});}
function redo(){return perf.measureAction('redo',()=>{const target=historyManager.peekRedo();if(!target)return;const ids=target.pages.map(p=>p.id);restore(historyManager.redo(snapshot(ids)));});}
function setView(v,{redraw=true}={}){view=v;svg.setAttribute('viewBox',v.join(' '));$('zoom-label').textContent=page()?Math.round(page().width/view[2]*100)+'%':'100%';if(redraw)draw();}
function fit(){if(page())setView([0,0,page().width,page().height]);}
function point(e){const m=svg.getScreenCTM();if(!m)return[0,0];const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(m.inverse());return[Math.max(0,Math.min(page().width,p.x)),Math.max(0,Math.min(page().height,p.y))];}
function zoom(f,anchor,{redraw=true}={}){if(!page())return;const [x,y,w,h]=view,nw=Math.max(page().width/40,Math.min(page().width*2,w*f)),ratio=nw/w,a=anchor??[x+w/2,y+h/2];setView([a[0]-(a[0]-x)*ratio,a[1]-(a[1]-y)*ratio,nw,h*ratio],{redraw});}
function syncPhoto(){const p=page(),photo=$('photo');photo.setAttribute('width',p?.width??0);photo.setAttribute('height',p?.height??0);$('empty').hidden=!!p;if(!p){photo.setAttribute('href','');return;}if(p.src){photo.setAttribute('href',p.src);return;}photo.setAttribute('href','');if(p.assetRef)void ensureImageLoaded(p).then(source=>{if(page()?.id===p.id)photo.setAttribute('href',source);}).catch(error=>toast(error.message));}
function switchPage(id,preserveView=false){return perf.measureAction('switch-page',()=>{if(draft.length)toast(t('canvas.unfinishedCancelled'));const previous=page(),keptView=[...view];if(previous?.id!==id){if(previous?.assetRef&&previous.src&&!appSettings.cacheImagesInMemory)delete previous.src;if(previous?.inferenceRef&&previous.inference)delete previous.inference;}active=id;clearSelection();marquee=null;draft=[];tool='select';scaleDraft=null;const target=page();applicationState.setWorkspaceMode(isMeasurementResultPage(target)?appSettings.defaultWorkspaceMode:'measure');const pool=$('inspect-show-pool');if(pool)pool.checked=Boolean(isMeasurementResultPage(target)&&appSettings.showRelatedCandidates);syncPhoto();if(preserveView&&previous?.width===page()?.width&&previous?.height===page()?.height)setView(keptView);else fit();render();});}
function setTool(t){if(!page())return toast(t('common.importImageFirst'));if(['line','polygon','box'].includes(t)&&uiState.activeDisplayLayer!=='edits'){applicationState.setDisplayLayer('edits');applicationState.setSelectedLayerObject(null);maskRenderKey='';syncDisplayLayerButtons();}if(t==='line'&&!group())return toast(t('canvas.selectSpikeletFirst'));if(t==='line'&&tool!=='line'){checkpoint();group().line=[];group().modified=true;group().confirmed=false;changed({panels:false});}draft=[];node=null;selectedNodes=[];marquee=null;if(t==='line'||t==='polygon')selectedKind=t;tool=t;render({panels:true,canvas:true,tools:true});svg.focus();}
const groupById=id=>page()?.groups.find(g=>g.uid===id);
const inspectionRecord=()=>page()?.inference&&selected?inspectionRecordForSpikelet(page().inference,selected):null;
const inspectionBranch=()=>{
 const record=inspectionRecord(),branches=record?._candidate_branches??[];
 return branches[uiState.inspectionBranchIndex]??branches[0]??null;
};
function el(name,attrs,parent=$('annotations')){const e=document.createElementNS(NS,name);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);parent.appendChild(e);return e;}
function drawInspectionOverlay(){
 renderInspectionOverlayLayer({
  root:$('inspection-layer'),
  record:inspectionRecord(),
  branch:inspectionBranch(),
  workspaceMode:uiState.workspaceMode,
  ctrl:sourcePreviewActive(),
  displayLayer:uiState.activeDisplayLayer,
  inspectionStep:uiState.inspectionStep,
  inspectionBranchIndex:uiState.inspectionBranchIndex,
  showPool:Boolean($('inspect-show-pool')?.checked)
 });
}
function draw(){
 drawMasks();
 drawInspectionOverlay();
 $('original-badge').hidden=!sourcePreviewActive();$('original-badge').textContent=sourcePreviewPinned?t('canvas.originalPreviewPinned'):t('canvas.originalPreview');
 renderEditableAnnotations({
  root:$('annotations'),
  draftRoot:$('draft'),
  page:page(),
  editsVisible:!sourcePreviewActive()&&uiState.activeDisplayLayer==='edits',
  screenScale:svg.getScreenCTM()?.a||1,
  workspaceMode:uiState.workspaceMode,
  tool,
  objectSelected,
  nodeSelected,
  selectedNode:node,
  scaleDraft,
  draft,
  marquee
 });
}
function refreshAnnotationSelection(geometryGroup=null){
 if(uiState.activeDisplayLayer!=='edits')return;
 const root=$('annotations'),screenScale=svg.getScreenCTM()?.a||1,r=7/screenScale;
 if(geometryGroup)updateEditableGeometry({root,group:geometryGroup,screenScale});
 for(const polygon of root.querySelectorAll('polygon[data-kind="polygon"]')){
  const chosen=objectSelected(polygon.dataset.group,'polygon');
  polygon.setAttribute('fill',chosen?'#44896430':'#44896415');
  polygon.setAttribute('stroke',chosen?'#225d40':'#4c8d66');
  polygon.setAttribute('stroke-width',chosen?'2':'1');
 }
 for(const line of root.querySelectorAll('polyline[data-kind="line"]:not([data-hit="line"])')){
  const chosen=objectSelected(line.dataset.group,'line');
  line.setAttribute('stroke',chosen?'#d18d18':'#d4a33d');
  line.setAttribute('stroke-width',chosen?'4':'2.5');
 }
 for(const circle of root.querySelectorAll('circle.node'))circle.remove();
 if(uiState.workspaceMode==='measure'&&(tool==='select'||tool==='box')){
  for(const item of selectedObjects){const g=groupById(item.uid);if(!g)continue;const kind=item.kind;for(const [i,p] of g[kind].entries()){const attrs={cx:p[0],cy:p[1],class:'node','data-group':g.uid,'data-kind':kind,'data-index':i};el('circle',{...attrs,r:13/screenScale,fill:'transparent','pointer-events':'all','data-hit':'node'},root);el('circle',{...attrs,r,fill:nodeSelected(g.uid,kind,i)||node?.uid===g.uid&&node.kind===kind&&node.index===i?'#d18d18':'white',stroke:kind==='line'?'#c38722':'#245c48','stroke-width':2,'vector-effect':'non-scaling-stroke','pointer-events':'none'},root);}}
 }
}
function calibrationMmPerPx(target){
 const c=target?.calibration;if(!c)return null;
 const px=pathLength(c.points??[]),mm=Number(c.mm);
 return px>0&&Number.isFinite(mm)&&mm>0?mm/px:null;
}
function sameLine(a,b){if(a===b)return true;if(!Array.isArray(a)||!Array.isArray(b)||a.length!==b.length)return false;for(let i=0;i<a.length;i++)if(a[i]?.[0]!==b[i]?.[0]||a[i]?.[1]!==b[i]?.[1])return false;return true;}
function applyConfidenceFilterToPage(target,threshold,{clearConfirmed=true}={}){
 if(!target||!Array.isArray(target.groups)||!target.inference)return false;
 const cutoff=Math.max(0,Math.min(1,Number(threshold)||0)),mmPerPx=calibrationMmPerPx(target);
 target.confidenceThreshold=cutoff;
 if(!Number.isFinite(mmPerPx)||mmPerPx<=0)return false;
 let changedAny=false;
 for(const g of target.groups){
  if(g.origin!=='automatic'||g.modified)continue;
  if(!Array.isArray(g.autoLine))g.autoLine=clone(g.line??[]);
  const record=inspectionRecordForSpikelet(target.inference,g.uid);
  const next=confidenceFilteredLine({baseline:g.autoLine,record,threshold:cutoff,mmPerPx});
  if(sameLine(g.line,next))continue;
  g.line=next;
  g.confidenceFiltered=cutoff>0&&!sameLine(g.autoLine,next);
  if(clearConfirmed)g.confirmed=false;
  changedAny=true;
 }
 return changedAny;
}
function syncConfidenceFilterControl(target){
 const control=$('confidence-filter-control'),slider=$('confidence-filter'),value=$('confidence-filter-value');
 const available=Boolean(target&&isMeasurementResultPage(target));
 control.hidden=!available;
 if(!available)return;
 const threshold=Math.max(0,Math.min(1,Number(target.confidenceThreshold)||0));
 slider.value=threshold.toFixed(2);value.textContent=threshold.toFixed(2);
 slider.disabled=!target.inference||!target.calibration;
}
function fmt(g){const n=lengthMM(g,page()?.calibration);return n===null?'—':n.toFixed(2);}
function reviewStatus(g){return effectiveReviewStatus(g);}
function reviewStatusLabel(g){return t(`review.status.${reviewStatus(g)}`);}
function matchesReviewFilter(g){const status=reviewStatus(g);if(uiState.reviewFilter==='all')return true;return status===uiState.reviewFilter;}
function syncReviewSelection(g){if(!g)return;const reasons=reviewStatus(g)==='needs_review'?reviewReasonLabels(g):[];$('review-selected-label').textContent=t('canvas.spikeletAria',{id:g.name});$('review-selected-status').textContent=reviewStatusLabel(g);$('review-selected-reasons').hidden=!reasons.length;$('review-selected-reasons').textContent=reasons.join(' · ');$('confirm-selected').textContent=g.confirmed?t('review.reopen'):t('review.confirm');$('confirm-selected').disabled=g.line.length<2;}
function metric(value,digits=2,suffix=''){if(value==null||value==='')return'—';const number=Number(value);return Number.isFinite(number)?number.toFixed(digits)+suffix:String(value);}
async function setWorkspaceMode(mode){if(!['measure','inspect'].includes(mode))return;if(mode==='inspect'&&isMeasurementResultPage(page())&&!page()?.inference){try{await ensureInferenceLoaded(page());}catch(error){toast(error.message);return;}}const changedMode=uiState.workspaceMode!==mode;if(changedMode){applicationState.setWorkspaceMode(mode);tool='select';draft=[];selectedNodes=[];node=null;marquee=null;applicationState.setInspectionStep(0);render({panels:true,canvas:true,tools:true});svg.focus();}const panel=document.querySelector('.results');if(panel)panel.scrollTop=0;}
function setInspectionStep(value){const record=inspectionRecord(),branch=inspectionBranch();if(!record){applicationState.setInspectionStep(0);return;}const steps=branch?.hops??record.steps??[],max=steps.length+(uiState.inspectionBranchIndex===0&&record.representative?1:0);applicationState.setInspectionStep(Math.min(max,Number(value)||0));renderInspectionPanel();drawInspectionOverlay();}
function renderWorkspaceMode(){
 for(const button of document.querySelectorAll('[data-workspace-mode]'))button.setAttribute('aria-pressed',String(button.dataset.workspaceMode===uiState.workspaceMode));
 $('measure-pane').hidden=uiState.workspaceMode!=='measure';
 $('inspect-pane').hidden=uiState.workspaceMode!=='inspect';
 syncCanvasActionButtons();
}
function renderInspectionPanel(){
 const g=group(),record=inspectionRecord(),branch=inspectionBranch(),empty=$('inspect-empty'),content=$('inspect-content');
 $('inspect-focus').disabled=!g;
 if(!g||!record){
  content.hidden=true;empty.hidden=false;
  empty.textContent=!g?t('inspect.empty'):t('inspect.unavailable');
  return;
 }
 empty.hidden=true;content.hidden=false;
 const branches=record._candidate_branches??[],steps=branch?.hops??record.steps??[],isWinner=uiState.inspectionBranchIndex===0,hasRepresentative=isWinner&&Boolean(record.representative),max=steps.length+(hasRepresentative?1:0);
 applicationState.setInspectionStep(Math.min(max,uiState.inspectionStep));
 const seedId=branch?.seed?.support_hypothesis_id??record.winner_seed?.support_hypothesis_id;
 const seed=(record.seed_candidates??[]).find(item=>item.support_hypothesis_id===seedId)??record.winner_seed;
 $('inspect-title').textContent=`${t('canvas.spikeletAria',{id:g.name})}${branches.length>1?` · Branch ${uiState.inspectionBranchIndex+1}/${branches.length}`:''}`;
 $('inspect-seed-mode').textContent=seed?.mode??record.winner?.seed_mode??'—';
 $('inspect-hop-count').textContent=String(steps.length);
 $('inspect-final-length').textContent=metric(isWinner?(record.representative?.length_mm_internal??record.winner?.final_length_mm):branch?.final_length_mm,2,' mm');
 $('inspect-branch-count').textContent=branches.length?String(branches.length):(record.winner?String(1+(record.alternatives?.length??0)):'—');
 const slider=$('inspect-step-slider');slider.max=String(max);slider.value=String(uiState.inspectionStep);slider.disabled=max===0;
 $('inspect-step-back').disabled=uiState.inspectionStep<=0;$('inspect-step-forward').disabled=uiState.inspectionStep>=max;
 let label,detail=[];
 if(uiState.inspectionStep===0){
  label=t('inspect.stage.seed');
  detail=[[t('inspect.detail.support'),seed?.support_hypothesis_id],[t('inspect.detail.mode'),seed?.mode],[t('inspect.detail.seedScore'),metric(seed?.seed_score)],[t('inspect.detail.rootDistance'),metric(seed?.root_distance_mm,2,' mm')],[t('inspect.detail.projectionDistance'),metric(seed?.projection_distance_mm,2,' mm')],[t('inspect.detail.confidence'),metric(seed?.confidence,3)]];
 }else if(uiState.inspectionStep<=steps.length){
  const step=steps[uiState.inspectionStep-1];label=t('inspect.stage.hop',{current:uiState.inspectionStep,total:steps.length});
  detail=[[t('inspect.detail.support'),step.support_hypothesis_id],[t('inspect.detail.extension'),metric(step.extension_mm,2,' mm')],[t('inspect.detail.distance'),metric(step.distance_mm,2,' mm')],[t('inspect.detail.joinAngle'),metric(step.join_angle_deg,1,'°')],[t('inspect.detail.trendAngle'),metric(step.trend_angle_deg,1,'°')],['Multiscale angle',metric(step.multiscale_angle_deg,1,'°')],['Local turn',metric(step.join_local_turn_deg,1,'°')],['Excess turn',metric(step.join_excess_turn_deg,1,'°')],[t('inspect.detail.growthScore'),metric(step.growth_score)],[t('inspect.detail.ownership'),step.ownership_mode??'—']];
 }else{
  const rep=record.representative;label=t('inspect.stage.representative');
  detail=[[t('inspect.detail.candidate'),rep?.candidate_id],[t('inspect.stage.seed'),rep?.seed_hypothesis_id],[t('inspect.detail.internalLength'),metric(rep?.length_mm_internal,2,' mm')],[t('inspect.growthHops'),rep?.growth_hops??steps.length]];
 }
 $('inspect-step-label').textContent=label;$('inspect-stage-badge').textContent=label;
 const dl=$('inspect-step-detail');dl.replaceChildren();for(const [name,value] of detail){const dt=document.createElement('dt');dt.textContent=name;const dd=document.createElement('dd');dd.textContent=value??'—';dl.append(dt,dd);}
}
function renderPanels(){const p=page(),g=group();if(p?.inference)hydrateReviewTriage(p,p.inference);else if(p?.inferenceRef&&isMeasurementResultPage(p))void ensureInferenceLoaded(p).then(()=>render({panels:true,images:false,canvas:true,tools:false})).catch(()=>{});syncConfidenceFilterControl(p);$('image-count').textContent=navigationPages(project.pages).length;$('image-title').textContent=p?.name??t('canvas.startMeasurement');const resolutionTag=p?.resolutionEnhancement?.applied?' · Low-resolution input · upscaled':'';$('image-meta').textContent=p?`${p.width} × ${p.height} px · ${p.demo?t('canvas.sourceHistorical'):t('canvas.sourceLocal')} · ${p.calibration?t('canvas.calibrated'):t('canvas.calibrationRequired')}${resolutionTag}`:t('canvas.importOrSample');const calibrationRatio=p?.calibration?(p.calibration.mm/pathLength(p.calibration.points)):null;$('calibration-open').textContent=calibrationRatio!==null?`${calibrationRatio.toFixed(5)} mm/px`:'⌁ Not calibrated';$('calibration-open').disabled=calibrationRatio===null;$('recalibrate').hidden=!p;$('group-count').textContent=t('canvas.spikeletCount',{count:p?.groups.length??0});
 $('rows').replaceChildren();for(const button of document.querySelectorAll('[data-review-filter]'))button.setAttribute('aria-pressed',String(button.dataset.reviewFilter===uiState.reviewFilter));const groups=(p?.groups??[]).filter(g=>g.name.toLowerCase().includes($('search').value.toLowerCase())&&matchesReviewFilter(g));$('no-results').hidden=groups.length>0;
 for(const item of groups){const tr=document.createElement('tr');tr.className=selectedObjects.some(o=>o.uid===item.uid)?'active':'';tr.tabIndex=0;tr.dataset.groupRow=item.uid;tr.setAttribute('aria-label',t('canvas.spikeletAria',{id:item.name}));for(const value of [item.name,fmt(item),reviewStatusLabel(item)]){const td=document.createElement('td');td.textContent=value;tr.appendChild(td);}tr.onclick=()=>select(item.uid,appSettings.autoFocusSelection,'polygon',false,'list');tr.onkeydown=e=>{if(e.key==='Enter'&&!(tool==='select'&&selected)){e.preventDefault();e.stopPropagation();select(item.uid,appSettings.autoFocusSelection,'polygon',false,'list');}};tr.cells[0].ondblclick=()=>{$('group-name').focus();$('group-name').select();};$('rows').appendChild(tr);}
 $('editor').hidden=!g;$('edit-empty').hidden=!!g;if(g){if(document.activeElement!==$('group-name'))$('group-name').value=g.name;$('selected-length').textContent=fmt(g)+(p.calibration?' mm':'');}
 $('review-actions').hidden=!g;if(g)syncReviewSelection(g);
 renderWorkspaceMode();renderInspectionPanel();
 $('undo').disabled=!historyManager.canUndo||uiState.workspaceMode!=='measure';$('redo').disabled=!historyManager.canRedo||uiState.workspaceMode!=='measure';$('export').disabled=!p;$('save-project').disabled=!p;updateInferenceActions();
}
function removePage(id){const target=project.pages.find(p=>p.id===id);if(!target||!confirm(t('canvas.removeOneConfirm',{name:target.name})))return;const deleting=cascadePageIds(project.pages,new Set([id]));project.pages=project.pages.filter(p=>!deleting.has(p.id));if(deleting.has(active)){const first=navigationPages(project.pages)[0],next=first?navigationTarget(first,project.pages):null;active=next?.id??null;clearSelection();syncPhoto();if(active)fit();else{view=[0,0,100,100];svg.setAttribute('viewBox',view.join(' '));}}historyManager.clear();render();changed({structural:true});}
let imageCardObserver=null;
function observeImageCard(img,p){
 if(p.src){img.src=p.src;return;}
 if(!p.assetRef)return;
 if(!imageCardObserver&&typeof IntersectionObserver==='function')imageCardObserver=new IntersectionObserver(entries=>{for(const entry of entries){if(!entry.isIntersecting)continue;imageCardObserver.unobserve(entry.target);const pageId=entry.target.dataset.pageId,target=project.pages.find(item=>item.id===pageId);if(target?.assetRef)void loadImageAsset(target.assetRef).then(source=>entry.target.src=source).catch(()=>{});}}, {root:$('image-list'),rootMargin:'240px'});
 img.dataset.pageId=p.id;
 if(imageCardObserver)imageCardObserver.observe(img);else void loadImageAsset(p.assetRef).then(source=>img.src=source).catch(()=>{});
}
function renderImages(){
 const roots=navigationPages(project.pages),ids=new Set(roots.map(p=>p.id));for(const id of selectedImages)if(!ids.has(id))selectedImages.delete(id);
 imageCardObserver?.disconnect();$('image-list').replaceChildren();
 const activePage=page();
 for(const p of roots){const target=navigationTarget(p,project.pages)??p,wrap=document.createElement('div');wrap.className='image-card-wrap';const pick=document.createElement('input');pick.type='checkbox';pick.className='image-select';pick.checked=selectedImages.has(p.id);pick.setAttribute('aria-label',t('canvas.selectImageAria',{name:p.name}));pick.onchange=()=>{pick.checked?selectedImages.add(p.id):selectedImages.delete(p.id);syncImageBatchTools();};const b=document.createElement('button');const cardActive=active===p.id||activePage?.sourcePageId===p.id;b.className='image-card'+(cardActive?' active':'');const img=document.createElement('img');img.alt='';img.loading='lazy';observeImageCard(img,p);const name=document.createElement('span');name.textContent=p.name;const sub=document.createElement('small');const status=projectPageStatus(p,project.pages);sub.textContent=status==='result'?t('canvas.statusResult',{count:p.groups.length}):status==='measured'?t('canvas.statusMeasured'):status==='ready'?t('canvas.statusReady'):t('canvas.statusNeedsCalibration');b.append(img,name,sub);b.onclick=()=>switchPage(target.id);wrap.append(pick,b);$('image-list').appendChild(wrap);}
 syncImageBatchTools();
}
function syncImageBatchTools(){const all=$('select-all-images'),count=selectedImages.size,total=navigationPages(project.pages).length;all.checked=total>0&&count===total;all.indeterminate=count>0&&count<total;all.disabled=!total;$('delete-selected-images').disabled=!count;$('delete-selected-images').textContent=count?t('canvas.deleteCount',{count}):t('action.delete');}
async function deleteSelectedImages(){const count=selectedImages.size;if(!count)return;if(!confirm(t('canvas.removeManyConfirm',{count})))return;const deleting=cascadePageIds(project.pages,selectedImages),remaining=project.pages.filter(p=>!deleting.has(p.id)),clearingAll=POSTPROCESS_LAB&&navigationPages(remaining).length===0;project.pages=remaining;selectedImages.clear();if(deleting.has(active)){const first=navigationPages(project.pages)[0],next=first?navigationTarget(first,project.pages):null;active=next?.id??null;clearSelection();syncPhoto();if(active)fit();else{view=[0,0,100,100];svg.setAttribute('viewBox',view.join(' '));}}historyManager.clear();render();if(clearingAll){try{await persistence.discardPending();resetProjectToEmpty();await projectStore.clearCurrent();projectSyncChannel?.postMessage({type:'project-cleared'});$('save-status').textContent=t('status.savedLocal');}catch(error){toast(error.message);}}else changed({structural:true});toast(t('canvas.removedImages',{count}));}
$('select-all-images').onchange=e=>{selectedImages=e.target.checked?new Set(navigationPages(project.pages).map(p=>p.id)):new Set();render({panels:false,images:true,canvas:false,tools:false});};
$('delete-selected-images').onclick=deleteSelectedImages;
function renderToolState(){
 $('reset-demo').hidden=!page()?.demo;
 document.querySelectorAll('[data-tool]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.tool===tool));
 syncCanvasActionButtons();
 svg.classList.toggle('drawing',['polygon','line','scale','box'].includes(tool));
 $('drawing-bar').hidden=!['polygon','line'].includes(tool);
 $('finish').disabled=draft.length<(tool==='line'?2:3);
 $('finish').textContent=tool==='line'?t('draw.finishBind'):t('draw.finishSpikelet');
 $('drawing-count').textContent=tool==='line'?t('draw.representativeFor',{id:group()?.name??'',count:draft.length}):t('draw.vertices',{count:draft.length});
 $('hint').textContent=tool==='polygon'?t('draw.hintPolygon'):tool==='line'?t('draw.hintLine'):tool==='scale'?t('draw.hintScale'):tool==='box'?t('draw.hintBox'):t('draw.hintSelect');
}
const measuredRender=(name,fn)=>()=>{const started=perf.start();try{return fn();}finally{perf.end(`render.${name}`,started);}};
const renderScheduler=createRenderScheduler({
 handlers:{
  panels:measuredRender('panels',renderPanels),
  images:measuredRender('images',renderImages),
  canvas:measuredRender('canvas',draw),
  tools:measuredRender('tools',renderToolState)
 },
 order:['panels','images','canvas','tools'],
 onFlush:({durationMs})=>perf.record('render.flush',durationMs)
});
function render(domains={panels:true,images:true,canvas:true,tools:true}){
 renderScheduler.request(Object.entries(domains).filter(([,enabled])=>enabled).map(([domain])=>domain));
}
function refreshMeasureSelectionUI(){
 const g=group(),p=page();
 for(const tr of $('rows').children)tr.classList.toggle('active',tr.dataset.groupRow===selected);
 $('editor').hidden=!g;$('edit-empty').hidden=!!g;
 if(g){if(document.activeElement!==$('group-name'))$('group-name').value=g.name;$('selected-length').textContent=fmt(g)+(p?.calibration?' mm':'');}
 $('review-actions').hidden=!g;
 if(g)syncReviewSelection(g);
 renderWorkspaceMode();
}
function select(id,focus=false,kind='polygon',add=false,source='canvas'){return perf.measureAction('select',()=>{if(uiState.activeDisplayLayer==='edits')applicationState.setWorkspaceMode('measure');if(id!==selected)applicationState.setInspectionStep(0);if(!add)clearSelection();selectedKind=kind;selected=id;if(id&&!objectSelected(id,kind))selectedObjects.push({uid:id,kind});node=null;if(tool!=='select'&&tool!=='box')setTool('select');$('group-name').value=group()?.name??'';$('name-error').textContent='';refreshMeasureSelectionUI();refreshAnnotationSelection();if(source==='canvas')document.querySelector(`[data-group-row="${CSS.escape(id)}"]`)?.scrollIntoView({block:'nearest'});if(focus)focusGroup();});}
function focusGroup(){const g=group();if(!g)return;const pts=[...g.polygon,...g.line],xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]),pad=page().width*.025;setView([Math.min(...xs)-pad,Math.min(...ys)-pad,Math.max(...xs)-Math.min(...xs)+pad*2,Math.max(...ys)-Math.min(...ys)+pad*2]);}
function finish(){if(tool==='polygon'){if(draft.length<3)return toast(t('draw.polygonMinVertices'));let area=0;draft.forEach((p,i)=>{const q=draft[(i+1)%draft.length];area+=p[0]*q[1]-p[1]*q[0];});if(Math.abs(area)<1)return toast(t('draw.polygonStraight'));checkpoint();const g={uid:uid(),name:nextName(page().groups),polygon:clone(draft),line:[],origin:'manual',modified:false,confirmed:false};page().groups.push(g);clearSelection();selected=g.uid;selectedKind='polygon';selectedObjects=[{uid:g.uid,kind:'polygon'}];toast(t('draw.spikeletCreated'));}else if(tool==='line'){if(draft.length<2||pathLength(draft)<.01)return toast(t('draw.lineMinPoints'));checkpoint();group().line=clone(draft);group().modified=true;group().confirmed=false;selectedKind='line';selectedObjects=[{uid:selected,kind:'line'}];toast(page().calibration?t('draw.boundUpdated',{id:group().name}):t('draw.boundNeedsCalibration',{id:group().name}));}else return;draft=[];tool='select';render({panels:true,canvas:true,tools:true});changed({panels:false});}
function edit(fn){if(!group())return;checkpoint();fn(group());if(group()){group().modified=true;group().confirmed=false;}render({panels:true,canvas:true,tools:true});changed({panels:false});}
svg.addEventListener('wheel',e=>{if(!page())return;e.preventDefault();zoom(Math.exp(Math.max(-100,Math.min(100,e.deltaY))*.002),point(e),{redraw:false});render({panels:false,images:false,canvas:true,tools:false});},{passive:false});
svg.addEventListener('pointerdown',e=>{if(!page()||e.button>1)return;const target=e.target;const pan=interaction.space||e.button===1||(tool==='select'&&!target.dataset.group);
 if(tool==='box'&&!interaction.space&&e.button===0){const start=point(e);marquee=[start,start];interaction.begin('box');svg.setPointerCapture(e.pointerId);e.preventDefault();draw();return;}
 if(['line','polygon','scale'].includes(tool)&&!interaction.space&&e.button===0){svg.focus();e.preventDefault();return;}
 if(pan){e.preventDefault();interaction.begin('pan',{x:e.clientX,y:e.clientY,view:[...view],matrix:svg.getScreenCTM().inverse()});svg.setPointerCapture(e.pointerId);svg.classList.add('panning');return;}
 if(uiState.workspaceMode==='measure'&&tool==='select'&&objectSelected(target.dataset.group,'line')&&target.dataset.kind==='line'&&!target.hasAttribute('data-index')&&e.detail<2){
  selected=target.dataset.group;selectedKind='line';
  const q=nearestSegment(group().line,point(e)),scale=svg.getScreenCTM()?.a||1;
  let index=group().line.findIndex(p=>distance(p,q.point)*scale<13);
  checkpoint();if(index<0){index=q.index+1;group().line.splice(index,0,q.point);group().modified=true;group().confirmed=false;}
  selectedNodes=[];node={uid:selected,kind:'line',index};interaction.begin('drag-node',{start:[e.clientX,e.clientY]});interaction.suppressNextClick();svg.setPointerCapture(e.pointerId);e.preventDefault();refreshAnnotationSelection(group());refreshMeasureSelectionUI();return;
 }
 if(uiState.workspaceMode==='measure'&&target.hasAttribute('data-index')&&tool==='select'){selected=target.dataset.group;selectedKind=target.dataset.kind;selectedNodes=[];node={uid:selected,kind:selectedKind,index:Number(target.dataset.index)};checkpoint();interaction.begin('drag-node',{start:[e.clientX,e.clientY]});svg.setPointerCapture(e.pointerId);e.preventDefault();}
});
svg.addEventListener('pointermove',e=>{if(!page())return;if(interaction.mode==='pan'){const drag=interaction.payload,m=drag.matrix,dx=(e.clientX-drag.x)*m.a,dy=(e.clientY-drag.y)*m.d;setView([drag.view[0]-dx,drag.view[1]-dy,...drag.view.slice(2)],{redraw:false});interaction.suppressNextClick();return;}const p=point(e);$('coordinates').textContent=`${p[0].toFixed(0)}, ${p[1].toFixed(0)} px`;if(interaction.mode==='drag-node'){const started=perf.start(),g=groupById(node.uid);if(!g)return;g[node.kind][node.index]=p;g.modified=true;g.confirmed=false;const root=$('annotations'),screenScale=svg.getScreenCTM()?.a||1;updateEditableGeometry({root,group:g,screenScale});updateEditableNodePosition({root,groupId:g.uid,kind:node.kind,index:node.index,point:p});if(g===group())$('selected-length').textContent=fmt(g)+(page()?.calibration?' mm':'');perf.end('action.drag-node-frame',started);interaction.suppressNextClick();}else if(interaction.mode==='box'){marquee[1]=p;updateMarqueeRect({root:$('draft'),marquee});interaction.suppressNextClick();}});
function insideBox(p,box){const x1=Math.min(box[0][0],box[1][0]),x2=Math.max(box[0][0],box[1][0]),y1=Math.min(box[0][1],box[1][1]),y2=Math.max(box[0][1],box[1][1]);return p[0]>=x1&&p[0]<=x2&&p[1]>=y1&&p[1]<=y2;}
function applyBox(){if(!marquee)return;clearSelection();for(const g of page().groups)for(const kind of ['polygon','line']){const indices=g[kind].map((p,i)=>insideBox(p,marquee)?i:-1).filter(i=>i>=0);if(!indices.length)continue;selectedObjects.push({uid:g.uid,kind});for(const index of indices)selectedNodes.push({uid:g.uid,kind,index});if(!selected){selected=g.uid;selectedKind=kind;}}toast(selectedNodes.length?t('draw.selectedVertices',{count:selectedNodes.length}):t('draw.noVertices'));marquee=null;refreshAnnotationSelection();refreshMeasureSelectionUI();render({canvas:true,tools:true});}
function release(){const previous=interaction.end(),wasPan=previous.mode==='pan';if(previous.mode==='drag-node'){changed({panels:false});refreshMeasureSelectionUI();}if(previous.mode==='box')applyBox();svg.classList.remove('panning');if(wasPan)draw();setTimeout(()=>interaction.releaseClickSuppression(),0);}
svg.addEventListener('pointerup',release);svg.addEventListener('pointercancel',release);
svg.addEventListener('click',e=>{if(!page()||interaction.suppressClick||interaction.space||sourcePreviewActive())return;const p=point(e);if(['polygon','line','scale'].includes(tool)){if(e.detail>1)return;draft.push(p);if(tool==='scale'&&draft.length===2){if(distance(...draft)<1){draft=[];return toast(t('draw.calibrationLineShort'));}scaleDraft=clone(draft);draft=[];tool='select';showScale('line');}render({canvas:true,tools:true});return;}if(tool==='box')return;if(e.target.hasAttribute('data-index')){refreshAnnotationSelection();refreshMeasureSelectionUI();return;}if(e.target.dataset.group)select(e.target.dataset.group,false,e.target.dataset.kind==='line'?'line':'polygon',e.shiftKey);else perf.measureAction('deselect',()=>{updateMaskSelection(null);clearSelection();refreshMeasureSelectionUI();refreshAnnotationSelection();});});
svg.addEventListener('dblclick',e=>{if(uiState.workspaceMode!=='measure'||tool!=='select'||!group()||e.target.dataset.group!==selected||e.target.dataset.kind!=='polygon'||e.target.hasAttribute('data-index'))return;e.preventDefault();e.stopPropagation();return perf.measureAction('double-click',()=>{const kind='polygon',q=nearestSegment(group()[kind],point(e),true),g=group();checkpoint();g[kind].splice(q.index+1,0,q.point);g.modified=true;g.confirmed=false;node={uid:selected,kind,index:q.index+1};selectedNodes=[];refreshAnnotationSelection(g);refreshMeasureSelectionUI();changed({panels:false});});});
function scaleMode(mode){const radio=document.querySelector(`[name="scale-mode"][value="${mode}"]`);if(radio)radio.checked=true;const auto=document.getElementById('scale-auto-fields');if(auto)auto.hidden=mode!=='auto';$('scale-line-fields').hidden=mode!=='line';}
async function showScale(mode=null){if(!page())return toast(t('common.importImageFirst'));const experiment=POSTPROCESS_LAB?await experimentCalibrationModule:null;if(experiment)experiment.installTwinCalibrationUI({autoGridEnabled:appSettings.autoGridCalibration});if(mode===null)mode=experiment?experiment.defaultMode(page().calibration,{autoGridEnabled:appSettings.autoGridCalibration}):'line';if(mode==='line'&&!scaleDraft)scaleDraft=clone(page().calibration?.source==='manual'?page().calibration?.points??null:null);if(mode!=='line')scaleDraft=null;$('scale-pixels').textContent=scaleDraft?t('calibration.linePixels',{pixels:pathLength(scaleDraft).toFixed(2)}):t('calibration.noLine');$('scale-value').value=page().calibration?.source==='manual'?page().calibration.mm:'';$('scale-unit').value='1';if($('scale-apply-matching')){$('scale-apply-matching').checked=false;$('scale-apply-matching').disabled=POSTPROCESS_LAB||isMeasurementResultPage(page());}experiment?.describeExistingGridCalibration?.(page().calibration);$('scale-error').textContent='';scaleMode(mode);$('scale-dialog').showModal();}
function showScaleEdit(){
 const current=page();if(!current?.calibration)return toast(t('calibration.noLine'));
 const ratio=current.calibration.mm/pathLength(current.calibration.points);
 $('scale-edit-ratio').value=Number.isFinite(ratio)?ratio.toFixed(8):'';
 $('scale-edit-error').textContent='';
 $('scale-edit-dialog').showModal();
 requestAnimationFrame(()=>{$('scale-edit-ratio').focus();$('scale-edit-ratio').select();});
}
$('scale-edit-form').onsubmit=e=>{
 e.preventDefault();
 const current=page(),ratio=Number($('scale-edit-ratio').value);
 if(!current?.calibration||!Number.isFinite(ratio)||ratio<=0){$('scale-edit-error').textContent=t('calibration.invalidRatio');return;}
 const linkedSource=POSTPROCESS_LAB&&isMeasurementResultPage(current)?sourceForMeasurement(current):null;
 const pageIds=[current.id,...(linkedSource&&linkedSource.id!==current.id?[linkedSource.id]:[])];
 checkpoint({pageIds});
 const calibration={points:[[0,0],[1,0]],mm:ratio,source:'direct'};
 current.calibration=calibration;
 if(linkedSource)linkedSource.calibration=clone(calibration);
 for(const g of current.groups)g.confirmed=false;
 $('scale-edit-dialog').close();
 render({panels:true,images:true,canvas:true,tools:true});
 changed({panels:false,pageIds});
};
for(const radio of document.querySelectorAll('[name="scale-mode"]'))radio.onchange=()=>scaleMode(radio.value);
$('draw-scale').onclick=()=>{$('scale-dialog').close();scaleDraft=null;setTool('scale');};$('scale-form').onsubmit=async e=>{e.preventDefault();const mode=document.querySelector('[name="scale-mode"]:checked').value;let calibration;const experiment=POSTPROCESS_LAB?await experimentCalibrationModule:null;if(mode==='auto'){try{experiment?.setGridStatus?.('Detecting the 5 mm background grid…');const current=page(),src=current?.src??await projectStore.loadAsset(current?.assetRef??current?.id);if(!src)throw Error('Stored source image is unavailable.');const detected=await experiment.calibrateFromGrid(src);const ratio=Number(detected.mm_per_px);if(!Number.isFinite(ratio)||ratio<=0)throw Error('Automatic grid calibration returned an invalid ratio.');let plausibility=null;if(appSettings.calibrationPlausibilityCheck){experiment?.setGridStatus?.('Checking spikelet-scale plausibility…');plausibility=await experiment.assessCalibrationPlausibility(src,ratio);const plausibilityMessage=experiment.plausibilityErrorMessage(plausibility);if(plausibilityMessage){alert(plausibilityMessage);throw Error('Automatic calibration failed biological plausibility check.');}}calibration={points:[[0,0],[1,0]],mm:ratio,source:'grid',gridCalibration:{...detected},...(plausibility?{calibrationPlausibility:plausibility}:{})};const bioStatus=!appSettings.calibrationPlausibilityCheck?' · plausibility check disabled':plausibility?.adequate===true?` · spikelet median ${Number(plausibility.median_long_side_mm).toFixed(2)} mm`:plausibility?.adequate==null?' · spikelet check unavailable':'';experiment.setGridStatus(`Estimated ${ratio.toFixed(8)} mm/px · ${detected.qc_adequate?'QC passed':'QC warning'}${bioStatus}`);}catch(error){$('scale-error').textContent=error.message;experiment?.setGridStatus?.('Automatic grid calibration failed.');return;}}else{const mm=Number($('scale-value').value)*Number($('scale-unit').value);if(!scaleDraft||!Number.isFinite(mm)||mm<=0){$('scale-error').textContent=t('calibration.invalidLineLength');return;}calibration={points:clone(scaleDraft),mm,source:'manual'};}const current=page(),linkedSource=POSTPROCESS_LAB&&isMeasurementResultPage(current)?sourceForMeasurement(current):null,matching=POSTPROCESS_LAB?[]:($('scale-apply-matching').checked?matchingUncalibratedSources(project.pages,current):[]);const calibrationPageIds=[current.id,...(linkedSource&&linkedSource.id!==current.id?[linkedSource.id]:[]),...matching.map(target=>target.id)];checkpoint({pageIds:calibrationPageIds});current.calibration=calibration;if(linkedSource)linkedSource.calibration=clone(calibration);for(const g of current.groups)g.confirmed=false;let applied=0;for(const target of matching){target.calibration=clone(calibration);for(const g of target.groups)g.confirmed=false;applied++;}scaleDraft=null;$('scale-dialog').close();render({panels:true,images:true,canvas:true,tools:true});changed({panels:false,pageIds:calibrationPageIds});if(applied)toast(t('calibration.appliedMatching',{count:applied}));const continuation=POSTPROCESS_LAB?pendingCalibrationContinuation:null;pendingCalibrationContinuation=null;if(continuation==='run')queueMicrotask(()=>runCurrentMeasurement());else if(continuation==='rerun')queueMicrotask(()=>rerunCurrentMeasurement());else if(appSettings.runAfterCalibration){const source=sourceForMeasurement(current),modelId=selectedModelId();if(modelAvailable&&source&&modelId&&!hasMeasurementResult(project.pages,source.id,modelId))queueMicrotask(()=>runCurrentMeasurement());}};
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>{if(POSTPROCESS_LAB&&b.dataset.close==='scale-dialog')pendingCalibrationContinuation=null;$(b.dataset.close).close();});document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>setTool(b.dataset.tool));
$('scale-dialog').addEventListener('cancel',()=>{if(POSTPROCESS_LAB)pendingCalibrationContinuation=null;});

$('calibration-open').onclick=()=>showScaleEdit();$('recalibrate').onclick=()=>{if(POSTPROCESS_LAB)pendingCalibrationContinuation=null;return showScale();};$('fit').onclick=fit;$('zoom-in').onclick=()=>zoom(.8);$('zoom-out').onclick=()=>zoom(1.25);$('undo').onclick=undo;$('redo').onclick=redo;$('source-preview-toggle').onclick=()=>{if(!page())return;sourcePreviewPinned=!sourcePreviewPinned;maskRenderKey='';render({panels:false,images:false,canvas:true,tools:true});};$('canvas-delete-selection').onclick=deleteSelection;$('canvas-focus-selection').onclick=focusGroup;$('finish').onclick=finish;$('cancel-draw').onclick=()=>setTool('select');$('redraw').onclick=()=>setTool('line');$('focus').onclick=focusGroup;$('inspect-focus').onclick=focusGroup;$('search').oninput=()=>render({panels:true,images:false,canvas:false,tools:false});
for(const button of document.querySelectorAll('[data-workspace-mode]'))button.onclick=()=>setWorkspaceMode(button.dataset.workspaceMode);
for(const button of document.querySelectorAll('[data-review-filter]'))button.onclick=()=>{applicationState.setReviewFilter(button.dataset.reviewFilter);render({panels:true,images:false,canvas:false,tools:false});};
$('confidence-filter').oninput=e=>{const p=page();if(!p?.inference||!p?.calibration)return;const threshold=Math.max(0,Math.min(1,Number(e.target.value)||0));$('confidence-filter-value').textContent=threshold.toFixed(2);applyConfidenceFilterToPage(p,threshold);render({panels:true,images:false,canvas:true,tools:false});};
$('confidence-filter').onchange=()=>{const p=page();if(!p)return;changed({panels:false,pageIds:[p.id]});};
$('confirm-selected').onclick=()=>{const g=group();if(!g)return;if(g.line.length<2)return toast(t('review.missingCannotConfirm'));checkpoint();g.confirmed=!g.confirmed;if(!matchesReviewFilter(g))clearSelection();render({panels:true,canvas:true,tools:true});changed({panels:false});};
$('inspect-step-slider').oninput=e=>setInspectionStep(e.target.value);$('inspect-step-back').onclick=()=>setInspectionStep(uiState.inspectionStep-1);$('inspect-step-forward').onclick=()=>setInspectionStep(uiState.inspectionStep+1);$('inspect-show-pool').onchange=drawInspectionOverlay;
function commitName(){const name=$('group-name').value.trim();if(!group())return;if(!validName(name,page().groups,selected)){$('name-error').textContent=t('editor.invalidId');$('group-name').value=group().name;return;}$('name-error').textContent='';if(name!==group().name)edit(g=>g.name=name);}
$('group-name').onchange=commitName;$('group-name').onblur=commitName;$('group-name').onkeydown=e=>{if(e.key==='Enter')e.target.blur();};$('group-name').oninput=()=>{$('name-error').textContent=group()&&!validName($('group-name').value,page().groups,selected)?t('editor.invalidId'):'';};
function removeAnnotationGroupDom(groupId){
 const root=$('annotations'),id=CSS.escape(groupId);
 for(const item of root.querySelectorAll(`[data-group="${id}"]`))item.remove();
}
function deleteSelectionImpl(){
 const nodes=selectedNodes.length?selectedNodes:node?[node]:[];
 if(nodes.length){
  checkpoint();const removed=new Set(),touched=new Set(),removedGroups=new Set();
  for(const {uid:groupId,kind} of nodes){const key=`${groupId}:${kind}`;if(removed.has(key))continue;removed.add(key);const g=groupById(groupId);if(!g)continue;const indices=new Set(nodes.filter(n=>n.uid===groupId&&n.kind===kind).map(n=>n.index));const keep=g[kind].filter((_,i)=>!indices.has(i));if(kind==='line'&&keep.length<2)g.line=[];else if(kind==='polygon'&&keep.length<3){page().groups=page().groups.filter(item=>item.uid!==groupId);removedGroups.add(groupId);}else g[kind]=keep;if(!removedGroups.has(groupId)){g.modified=true;g.confirmed=false;touched.add(groupId);}}
  clearSelection();
  for(const id of removedGroups)removeAnnotationGroupDom(id);
  for(const id of touched){const g=groupById(id);if(g)refreshAnnotationSelection(g);}
  refreshAnnotationSelection();refreshMeasureSelectionUI();
  if(removedGroups.size)render({panels:true,images:false,canvas:false,tools:false});
  toast(t('draw.deletedVertices',{count:nodes.length}));changed({panels:false});return;
 }
 if(!selectedObjects.length)return;
 if(appSettings.confirmDestructiveEdits&&!confirm('Delete the selected annotation object? This change can be undone.'))return;
 checkpoint();const removedGroups=new Set(),touched=new Set();
 for(const {uid:groupId,kind} of selectedObjects){const g=groupById(groupId);if(!g)continue;if(kind==='line'){g.line=[];g.modified=true;g.confirmed=false;touched.add(groupId);}else{page().groups=page().groups.filter(item=>item.uid!==groupId);removedGroups.add(groupId);}}
 clearSelection();
 for(const id of removedGroups)removeAnnotationGroupDom(id);
 for(const id of touched){const g=groupById(id);if(g)refreshAnnotationSelection(g);}
 refreshAnnotationSelection();refreshMeasureSelectionUI();render({panels:true,images:false,canvas:false,tools:false});
 toast(t('draw.deletedObjects'));changed({panels:false});
}
function deleteSelection(){return perf.measureAction('delete',deleteSelectionImpl);}
window.addEventListener('keydown',e=>{if(e.key==='Control'){interaction.setCtrl(true);draw();return;}const editing=/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)||document.querySelector('dialog[open]');if(editing)return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){if(uiState.workspaceMode!=='measure')return;e.preventDefault();e.shiftKey?redo():undo();return;}if(e.ctrlKey||e.metaKey)return;if(uiState.workspaceMode==='inspect'&&(e.key==='ArrowLeft'||e.key==='ArrowRight')){e.preventDefault();setInspectionStep(uiState.inspectionStep+(e.key==='ArrowRight'?1:-1));return;}if(e.code==='Space'){e.preventDefault();interaction.setSpace(true);}if(e.key==='Escape'){setTool('select');}if(e.key==='Enter'){e.preventDefault();if(tool==='select'||tool==='box'){clearSelection();render();svg.focus();}else if(uiState.workspaceMode==='measure')finish();}if(uiState.workspaceMode==='measure'&&(e.key==='Delete'||e.key==='Backspace')){e.preventDefault();deleteSelection();}const key=e.key.toLowerCase();const toolKey={v:'select',h:'select'}[key]??(uiState.workspaceMode==='measure'?{b:'box',p:'polygon',l:'line'}[key]:null);if(toolKey)setTool(toolKey);});window.addEventListener('keyup',e=>{if(e.key==='Control'){interaction.setCtrl(false);draw();}if(e.code==='Space')interaction.setSpace(false);});window.addEventListener('blur',()=>{release();interaction.resetTransient();draw();});window.addEventListener('resize',draw);
async function importImages(files){if(!ready)return 0;const accepted=[...files].filter(file=>['image/png','image/jpeg','image/webp'].includes(file.type)).sort((a,b)=>(a.webkitRelativePath||a.name).localeCompare(b.webkitRelativePath||b.name,undefined,{numeric:true}));if(!accepted.length){toast(t('import.noneSupported'));return 0;}let imported=0;for(const file of accepted){try{let src=await dataURL(file),[width,height]=await imageSize(src),resolutionEnhancement=null;if(POSTPROCESS_LAB&&appSettings.autoResolutionAdjustment){const gate=await resolutionGateModule;const prepared=await gate.prepareImportedImage({src,width,height,name:file.webkitRelativePath||file.name});if(!prepared)continue;src=prepared.src;width=prepared.width;height=prepared.height;resolutionEnhancement=prepared.resolutionEnhancement;}const id=uid();await projectStore.saveAsset(id,src);const p={id,name:file.webkitRelativePath||file.name,assetRef:id,width,height,groups:[],calibration:null,...(resolutionEnhancement?{resolutionEnhancement}: {})};project.pages.push(p);active=p.id;imported++;}catch(e){toast(`${file.name}: ${e.message}`);}}historyManager.clear();if(active)switchPage(active);changed({structural:true});if(imported)toast(t('import.imported',{count:imported}));if(appSettings.openCalibrationAfterImport&&page()&&!page().calibration)setTimeout(()=>showScale(),0);else if(!POSTPROCESS_LAB&&page()&&!page().calibration)showScale('line');return imported;}
for(const id of ['import','empty-import'])$(id).onclick=()=>$('import-dialog').showModal();$('choose-images').onclick=()=>{$('import-dialog').close();$('image-input').click();};$('choose-folder').onclick=()=>{$('import-dialog').close();$('folder-input').click();};for(const id of ['image-input','folder-input'])$(id).onchange=async e=>{await importImages(e.target.files);e.target.value='';};
const importDropzone=$('import-dropzone');let importDragDepth=0;const hasDraggedFiles=e=>Array.from(e.dataTransfer?.types??[]).includes('Files');const resetImportDropzone=()=>{importDragDepth=0;importDropzone.classList.remove('drag-active');};importDropzone.addEventListener('click',()=>{$('import-dialog').close();$('image-input').click();});importDropzone.addEventListener('keydown',e=>{if(e.key!=='Enter'&&e.key!==' ')return;e.preventDefault();$('import-dialog').close();$('image-input').click();});importDropzone.addEventListener('dragenter',e=>{if(!hasDraggedFiles(e))return;e.preventDefault();importDragDepth++;importDropzone.classList.add('drag-active');});importDropzone.addEventListener('dragover',e=>{if(!hasDraggedFiles(e))return;e.preventDefault();e.dataTransfer.dropEffect='copy';importDropzone.classList.add('drag-active');});importDropzone.addEventListener('dragleave',e=>{if(!hasDraggedFiles(e))return;e.preventDefault();importDragDepth=Math.max(0,importDragDepth-1);if(!importDragDepth)importDropzone.classList.remove('drag-active');});importDropzone.addEventListener('drop',async e=>{if(!hasDraggedFiles(e))return;e.preventDefault();const files=e.dataTransfer.files;resetImportDropzone();const count=await importImages(files);if(count&&$('import-dialog').open)$('import-dialog').close();});window.addEventListener('dragover',e=>{if(hasDraggedFiles(e))e.preventDefault();});window.addEventListener('drop',e=>{if(hasDraggedFiles(e))e.preventDefault();});$('import-dialog').addEventListener('close',resetImportDropzone);
$('save-project').onclick=async()=>{try{const snapshot=await buildHydratedProjectSnapshot(project,{includeImages:true,includeInference:true,loadAsset:ref=>projectStore.loadAsset(ref),loadInference:ref=>projectStore.loadInference(ref),normalizeInference:normalizeProductResult});download(new Blob([JSON.stringify(encodeProject(snapshot))],{type:'application/json'}),'awn-studio-project-'+new Date().toISOString().slice(0,10)+'.json');}catch(error){toast(error.message);}};$('open-project').onclick=()=>$('project-input').click();$('project-input').onchange=async e=>{try{const f=e.target.files[0];if(!f)return;const imported=decodeProject(JSON.parse(await f.text()));if(project.pages.length&&appSettings.confirmProjectReplace&&!confirm(t('project.openReplaceConfirm')))return;for(const p of navigationPages(imported.pages)){const[w,h]=await imageSize(p.src);if(w!==p.width||h!==p.height)throw Error(t('project.dimensionMismatch'));}project=imported;migrateCanonicalPaths(project);historyManager.clear();switchPage(project.pages[0].id);changed({structural:true});toast(t('project.opened'));}catch(err){toast(err.message);}e.target.value='';};
$('demo').onclick=async()=>{
 try{
  $('demo').disabled=true;
  const img=await fetch('./demo.jpg');if(!img.ok)throw Error(t('demo.imageUnavailable'));
  const src=await dataURL(await img.blob()),[width,height]=await imageSize(src),id=uid();
  await projectStore.saveAsset(id,src);
  const gridPx=width*(31.5/1920);
  const p={id,name:t('demo.name'),assetRef:id,width,height,groups:[],calibration:{points:[[80,80],[80+gridPx,80]],mm:5},demo:true,sample:true};
  project.pages.push(p);historyManager.clear();switchPage(p.id);changed({structural:true});toast(t('demo.loaded'));
 }catch(e){toast(e.message);}finally{$('demo').disabled=false;}
};
$('export').onclick=()=>{const pages=exportableMeasurementPages(project.pages);if(!pages.length)return toast(t('export.none'));const current=currentMeasurementPage(page(),project.pages),uncal=pages.filter(p=>!p.calibration).length,missing=pages.reduce((n,p)=>n+p.groups.filter(g=>g.line.length<2).length,0);$('export-summary').textContent=t('export.summary',{images:pages.length,spikelets:pages.reduce((n,p)=>n+p.groups.length,0),uncalibrated:uncal,missing});$('export-one').disabled=!current;$('export-dialog').showModal();};
const safeName=name=>name.replace(/[<>:"/\\|?*\x00-\x1f]/g,'_').slice(0,100);
$('export-one').onclick=()=>{const target=currentMeasurementPage(page(),project.pages);if(!target)return toast(t('export.none'));if(!target.calibration)return toast(t('export.calibrateCurrent'));download(new Blob([csv(target)],{type:'text/csv;charset=utf-8'}),safeName(target.sourceName??target.name)+'.csv');$('export-dialog').close();};$('export-detailed').onclick=async()=>{const pages=exportableMeasurementPages(project.pages);if(!pages.length)return toast(t('export.none'));if(pages.some(p=>!p.calibration))return toast(t('export.calibrateDetailed'));try{const snapshot=await buildHydratedProjectSnapshot(project,{includeInference:true,loadInference:ref=>projectStore.loadInference(ref),normalizeInference:normalizeProductResult});download(new Blob([detailedProjectCsv(snapshot.pages)],{type:'text/csv;charset=utf-8'}),'awn-studio-detailed-results.csv');$('export-dialog').close();}catch(error){toast(error.message);}};$('export-all').onclick=()=>{const pages=exportableMeasurementPages(project.pages);if(!pages.length)return toast(t('export.none'));if(pages.some(p=>!p.calibration))return toast(t('export.calibrateBatch'));download(zipFiles(pages.map((p,i)=>({name:`${i+1}_${safeName(p.sourceName??p.name)}.csv`,content:csv(p)}))),'awn-studio-results.zip');$('export-dialog').close();};
function migrateCanonicalPaths(target){let changed=false;for(const p of target.pages){if(p.inference?.pipeline!=='awnphen canonical physical closeout'||p.inference.path_simplification)continue;for(const g of p.groups){if(g.origin==='automatic'&&!g.modified&&g.line.length>=3){g.line=simplifyPathDP1(g.line,1);changed=true;}}p.inference.path_simplification='DP1 measurement path; tolerance 1 px';changed=true;}return changed;}
async function init(){try{const saved=appSettings.restoreLastProject?await projectStore.loadCurrent():null;if(saved){project=decodeProject(saved);let renumbered=false;for(const p of project.pages){if(p.demo&&!p.numberingVersion&&p.groups.every((g,i)=>g.name===String(i+1))){p.groups=readingOrder(p.groups);p.groups.forEach((g,i)=>g.name=String(i+1));p.numberingVersion=2;renumbered=true;}}const migrated=migrateCanonicalPaths(project),needsStorageSplit=project.pages.some(p=>(p.inference&&!p.inferenceRef)||(!p.sourcePageId&&p.src&&!p.assetRef));if(renumbered||migrated||needsStorageSplit)schedulePersist({full:true});switchPage(project.pages[0].id);$('save-status').textContent=t('status.restored');}}catch{$('save-status').textContent=t('status.manualSave');}finally{ready=true;render();}}init();

$('reset-demo').onclick=()=>{if(!page()?.demo)return;if(!confirm(t('demo.resetConfirm')))return;checkpoint();page().groups=[];clearSelection();draft=[];scaleDraft=null;tool='select';fit();render();changed();toast(t('demo.resetDone'));};

const inferenceClient=createInferenceClient();
function selectedModelId(){return selectedModel()?.id??null;}
function sourceForMeasurement(target=page()){if(!target)return null;if(!isMeasurementResultPage(target))return target;return project.pages.find(candidate=>candidate.id===target.sourcePageId)??null;}
function pendingSourcePages(){return collectPendingSourcePages(project.pages,selectedModelId());}
function uncalibratedPendingCount(){return uncalibratedPendingSourcePages(project.pages,selectedModelId()).length;}
function updateInferenceActions(){
 const current=page(),source=sourceForMeasurement(current),modelId=selectedModelId(),pending=pendingSourcePages().length,alreadyRan=Boolean(source&&modelId&&hasMeasurementResult(project.pages,source.id,modelId));
 $('run-model').disabled=!modelAvailable||inferenceRunning||!source||alreadyRan;
 $('rerun-model').disabled=!modelAvailable||inferenceRunning||!source||!alreadyRan;
 $('run-pending').disabled=!modelAvailable||inferenceRunning||pending===0;
 $('run-pending').textContent=pending?`${t('action.runPending')} (${pending})`:t('action.runPending');
 $('retry-model').hidden=modelAvailable;
 $('retry-model').disabled=inferenceRunning;
 $('stop-batch').hidden=!batchRunning;
 $('stop-batch').disabled=!batchRunning||batchStopRequested;
 $('model-select').disabled=!modelAvailable||inferenceRunning;
}
function selectedModel(){return modelCatalog.find(model=>model.id===$('model-select').value)??modelCatalog[0]??null;}
function configuredDefaultModelId(){
 if(appSettings.defaultModelId&&modelCatalog.some(model=>model.id===appSettings.defaultModelId&&model.available))return appSettings.defaultModelId;
 if(modelCatalogDefaultId&&modelCatalog.some(model=>model.id===modelCatalogDefaultId&&model.available))return modelCatalogDefaultId;
 return modelCatalog.find(model=>model.available)?.id??'';
}
function applyConfiguredDefaultModel(){
 const select=$('model-select'),target=configuredDefaultModelId();
 if(target&&[...select.options].some(option=>option.value===target&&!option.disabled))select.value=target;
 updateModelStatus();updateInferenceActions();
}
function populateSettingsModelSelect(){
 const select=$('setting-default-model');if(!select)return;
 select.replaceChildren(new Option('Service default',''));
 for(const model of modelCatalog){
  const option=new Option(model.name,model.id);option.disabled=!model.available;select.append(option);
 }
 select.value=[...select.options].some(option=>option.value===appSettings.defaultModelId)?appSettings.defaultModelId:'';
}
function populateModelSelect(catalog){
 modelCatalog=Array.isArray(catalog.models)?catalog.models:[];
 modelCatalogDefaultId=typeof catalog.default==='string'?catalog.default:null;
 const select=$('model-select');select.replaceChildren();
 for(const model of modelCatalog){
  const option=document.createElement('option');option.value=model.id;option.textContent=model.name;option.disabled=!model.available;select.append(option);
 }
 applyConfiguredDefaultModel();
 populateSettingsModelSelect();
}
function formatInferenceElapsed(ms){
 const seconds=Math.max(0,Number(ms)||0)/1000;
 if(seconds<60)return seconds.toFixed(1)+' s';
 const minutes=Math.floor(seconds/60),rest=Math.floor(seconds-minutes*60);
 return minutes+'m '+String(rest).padStart(2,'0')+'s';
}
function updateInferenceElapsed(){
 if(inferenceElapsedStartedAt==null)return;
 const badge=$('model-elapsed');badge.hidden=false;badge.textContent=formatInferenceElapsed(performance.now()-inferenceElapsedStartedAt);
}
function startInferenceElapsed(){
 if(inferenceElapsedTimer)clearInterval(inferenceElapsedTimer);
 inferenceElapsedStartedAt=performance.now();updateInferenceElapsed();
 inferenceElapsedTimer=setInterval(updateInferenceElapsed,100);
}
function stopInferenceElapsed(){
 if(inferenceElapsedStartedAt==null)return null;
 const elapsed=performance.now()-inferenceElapsedStartedAt;
 if(inferenceElapsedTimer)clearInterval(inferenceElapsedTimer);
 inferenceElapsedTimer=null;inferenceElapsedStartedAt=null;
 const badge=$('model-elapsed');badge.hidden=false;badge.textContent=formatInferenceElapsed(elapsed);
 return elapsed;
}
function resetInferenceElapsed(){
 if(inferenceElapsedTimer)clearInterval(inferenceElapsedTimer);
 inferenceElapsedTimer=null;inferenceElapsedStartedAt=null;
 const badge=$('model-elapsed');badge.hidden=true;badge.textContent='0.0 s';
}
function updateModelStatus(){
 const model=selectedModel();
 $('model-status').textContent=modelAvailable&&model?t('model.connected',{model:model.name,device:modelDevice==='cpu'?'CPU':'GPU'}):t('model.unavailable');
}
async function connectModel(){
 $('retry-model').disabled=true;
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),4000);
 try{
  const [m,catalog]=await Promise.all([
   inferenceClient.modelInfo({signal:controller.signal}),
   inferenceClient.models({signal:controller.signal}),
  ]);
  populateModelSelect(catalog);
  modelDevice=m.device;
  modelAvailable=modelCatalog.some(model=>model.available);
  $('model-status').textContent=modelAvailable?t('model.connected',{model:selectedModel()?.name??m.model,device:m.device==='cpu'?'CPU':'GPU'}):t('model.weightsUnavailable');
 }catch{modelAvailable=false;modelCatalog=[];$('model-select').replaceChildren(new Option('Unavailable',''));$('model-status').textContent=t('model.unavailable');}
 finally{clearTimeout(timeout);}
 updateInferenceActions();
}
function handleInferenceError(error){if(error?.code!=='service_unavailable')return false;modelAvailable=false;$('model-status').textContent=t('model.unavailable');updateInferenceActions();return true;}
function inferenceProgress(state){
 let bar=$('inference-progress');
 if(!bar){bar=document.createElement('progress');bar.id='inference-progress';bar.max=1;$('model-status').after(bar);}
 const running=['queued','running'].includes(state?.status);bar.hidden=!running;
 if(!running)return;
 if(state.total_tiles&&state.tiles>=0){bar.max=state.total_tiles;bar.value=state.tiles;}else{bar.removeAttribute('value');}
}
function preferredResultLayer(result){const desired=appSettings.defaultResultLayer;if(desired==='edits')return 'edits';const layers=displayLayersFromProductResult(result)??{};return Array.isArray(layers[desired])&&layers[desired].length?desired:'edits';}
function resetResultLayers(result=null){applicationState.setDisplayLayer(preferredResultLayer(result));applicationState.resetInspection();maskRenderKey='';syncDisplayLayerButtons();}
function measurementRequest(source){
 return {
  src:source.src,
  width:source.width,
  height:source.height,
  mm_per_px:source.calibration.mm/pathLength(source.calibration.points),
  model_id:selectedModel()?.id,
 };
}
const previewDelay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function playCompletionPreview(source,result){
 const layers=displayLayersFromProductResult(result)??{};
 const raw=layers.raw??[],candidates=layers.candidates??[],representatives=layers.representatives??[];
 const show=async(layer,stage,items,delayMs)=>{
  applicationState.setDisplayLayer(layer);syncDisplayLayerButtons();maskRenderKey='';
  const previewLayers=layer==='raw'?{raw:items}:{raw,[layer]:items};
  inferencePreview={pageId:source.id,revision:(inferencePreview?.revision??0)+1,stage,layers:previewLayers};
  draw();
  if(delayMs>0)await previewDelay(delayMs);
 };
 if(raw.length)await show('raw','raw',raw,520);
 const seeds=candidates.filter(item=>item.growth_stage==='seed');
 if(seeds.length)await show('candidates','seed',seeds,520);
 const hops=candidates.filter(item=>item.growth_stage==='hop');
 const maxHop=Math.max(0,...hops.map(item=>Number(item.hop??0)));
 for(let hop=1;hop<=maxHop;hop++){
  const visible=[...seeds,...hops.filter(item=>Number(item.hop??0)<=hop)];
  await show('candidates',`hop-${hop}`,visible,420);
 }
 if(representatives.length)await show('representatives','representatives',representatives,620);
}
function buildMeasurementResultPage(source,result){
 const groups=readingOrder(editableGroupsFromProductResult(result),result.run?.orientation?.rotation_deg);groups.forEach((g,i)=>g.name=String(i+1));
 const modelId=result.run?.model?.id??selectedModelId(),modelName=result.run?.model?.name??'automatic';
 const priorRuns=project.pages.filter(candidate=>candidate?.sourcePageId===source.id&&isMeasurementResultPage(candidate)&&measurementResultModelId(candidate)===modelId).length;
 const runNumber=priorRuns+1,baseName=t('result.pageName',{name:source.name,model:modelName}),name=runNumber>1?baseName+' · '+t('result.rerunSuffix',{run:runNumber}):baseName;
 const output={id:uid(),sourcePageId:source.id,sourceName:source.name,name,modelId,modelRun:runNumber,assetRef:source.assetRef??source.id,width:source.width,height:source.height,groups,calibration:clone(source.calibration),...(source.resolutionEnhancement?{resolutionEnhancement:clone(source.resolutionEnhancement)}:{}),demo:false,inference:result,pageKind:'measurement_result'};
 validateProject({schema:PROJECT_SCHEMA,pages:[output]});
 return output;
}
async function runAutomaticMeasurement(source,{activateResult=true,batchIndex=null,batchTotal=null}={}){
 if(!source)throw Error(t('common.importImageFirst'));
 if(isMeasurementResultPage(source))throw Error(t('batch.sourceOnly'));
 if(!source.calibration)throw Error(t('model.calibrateBeforeRun'));
 if(!source.src&&source.assetRef)await ensureImageLoaded(source);
 await ensureStoredImageAsset(source);
 const prefix=batchIndex==null?'':`[${batchIndex}/${batchTotal}] `;
 if(active!==source.id)switchPage(source.id);
 startInferenceElapsed();
 let job,state;
 try{
  $('model-status').textContent=prefix+t('model.submitting');
  job=await inferenceClient.submit(measurementRequest(source));
  inferencePreview={pageId:source.id,revision:0,stage:'waiting',layers:{}};draw();
  state=await inferenceClient.wait(job.id,{
   onState(nextState){$('model-status').textContent=prefix+nextState.message;inferenceProgress(nextState);},
   onPreview(preview){
    if(!appSettings.showLiveInferencePreview||preview.stage!=='raw')return;
    applicationState.setDisplayLayer('raw');syncDisplayLayerButtons();
    inferencePreview={pageId:source.id,revision:preview.revision,stage:preview.stage,layers:preview.layers};
    maskRenderKey='';draw();
   }
  });
 }catch(error){stopInferenceElapsed();throw error;}
 stopInferenceElapsed();
 if(state.status!=='done')throw Error(state.message??t('model.failed'));
 const result=normalizeProductResult(state.result),summary=resultSummary(result),output=buildMeasurementResultPage(source,result);
 output.inferenceRef=String(output.id);
 output.inferenceMeta={schema:result.schema??null,jobId:job.id,modelId:output.modelId};
 await projectStore.saveInference(output.inferenceRef,result);
 if(activateResult&&appSettings.showCompletionAnimation)await playCompletionPreview(source,result);else if(!activateResult)delete output.inference;
 project.pages.push(output);historyManager.clear();inferencePreview=null;resetResultLayers(result);
 if(activateResult)switchPage(output.id,true);else render({panels:true,images:true,canvas:true,tools:false});
 changed({structural:true});
 if(!activateResult&&source.assetRef)delete source.src;
 $('model-status').textContent=prefix+t('model.complete',{spikelets:summary.spikelet_count,awns:summary.measurement_path_count,seconds:summary.duration_seconds??'—'});
 return output;
}
async function runCurrentMeasurement(){
 const input=page(),source=sourceForMeasurement(input);if(!source)return toast(t('common.importImageFirst'));
 if(!source.calibration){if(POSTPROCESS_LAB){pendingCalibrationContinuation='run';showScale();}else showScale();return toast(t('model.calibrateBeforeRun'));}
 if(draft.length)return toast(t('common.finishDrawingFirst'));
 inferenceRunning=true;updateInferenceActions();
 try{
  await runAutomaticMeasurement(source,{activateResult:true});
  toast(t('model.openedForReview'));
 }catch(e){inferencePreview=null;draw();if(!handleInferenceError(e))$('model-status').textContent=t('model.didNotFinish',{message:e.message});toast(e.message);}
 finally{inferenceProgress(null);inferenceRunning=false;updateInferenceActions();}
}
async function rerunCurrentMeasurement(){
 const source=sourceForMeasurement(page()),modelId=selectedModelId();
 if(!source)return toast(t('common.importImageFirst'));
 if(!modelId||!hasMeasurementResult(project.pages,source.id,modelId))return;
 if(!source.calibration){if(POSTPROCESS_LAB){pendingCalibrationContinuation='rerun';showScale();}else showScale();return toast(t('model.calibrateBeforeRun'));}
 if(draft.length)return toast(t('common.finishDrawingFirst'));
 inferenceRunning=true;updateInferenceActions();
 try{
  await runAutomaticMeasurement(source,{activateResult:true});
  toast(t('model.openedForReview'));
 }catch(e){inferencePreview=null;draw();if(!handleInferenceError(e))$('model-status').textContent=t('model.didNotFinish',{message:e.message});toast(e.message);}
 finally{inferenceProgress(null);inferenceRunning=false;updateInferenceActions();}
}
async function runPendingMeasurements(){
 const queue=pendingSourcePages();if(!queue.length)return toast(t('batch.nonePending'));
 if(draft.length)return toast(t('common.finishDrawingFirst'));
 inferenceRunning=true;batchRunning=true;batchStopRequested=false;updateInferenceActions();let done=0,failed=0,lastOutput=null,processed=0,serviceUnavailable=false;
 let skipped=uncalibratedPendingCount();
 for(let i=0;i<queue.length;i++){
  const source=queue[i];
  $('model-status').textContent=t('batch.running',{current:i+1,total:queue.length,name:source.name});
  try{lastOutput=await runAutomaticMeasurement(source,{activateResult:false,batchIndex:i+1,batchTotal:queue.length});done++;}
  catch(e){failed++;inferencePreview=null;draw();serviceUnavailable=handleInferenceError(e)||serviceUnavailable;if(serviceUnavailable||!appSettings.continueBatchAfterError)batchStopRequested=true;toast(`${source.name}: ${e.message}`);}
  processed=i+1;
  if(batchStopRequested)break;
 }
 skipped+=Math.max(0,queue.length-processed);
 inferenceProgress(null);inferenceRunning=false;batchRunning=false;batchStopRequested=false;
 if(lastOutput)switchPage(lastOutput.id,true);else render();
 const message=t('batch.complete',{done,failed,skipped});if(!serviceUnavailable)$('model-status').textContent=message;toast(message);updateInferenceActions();
}
$('model-select').onchange=()=>{resetInferenceElapsed();updateModelStatus();updateInferenceActions();};
$('run-model').onclick=runCurrentMeasurement;
$('rerun-model').onclick=rerunCurrentMeasurement;
$('run-pending').onclick=runPendingMeasurements;
$('retry-model').onclick=connectModel;
$('stop-batch').onclick=()=>{if(!batchRunning)return;batchStopRequested=true;$('model-status').textContent=t('batch.stopping');updateInferenceActions();};
connectModel();

// Explicit report links open a real run as an uncalibrated, editable page.
async function openRunLink(){
 const jobId=new URLSearchParams(location.search).get('result');if(!jobId)return;
 if(!/^[a-f0-9]{32}$/.test(jobId))return toast(t('result.invalidLink'));
 while(!ready)await new Promise(resolve=>setTimeout(resolve,50));
 const existing=project.pages.find(p=>p.inference?.jobId===jobId||p.inferenceMeta?.jobId===jobId);
 if(existing){switchPage(existing.id);return;}
 try{
  const base=`/runs/awn_studio/${jobId}/`;
  const response=await fetch(base+'result.json');if(!response.ok)throw Error(t('result.notFound'));
  const stored=await response.json(),img=await fetch(base+'input.png');if(!img.ok)throw Error(t('result.sourceNotFound'));
  const result=normalizeProductResult(stored),src=await dataURL(await img.blob()),[width,height]=await imageSize(src),groups=readingOrder(editableGroupsFromProductResult(result),result.run?.orientation?.rotation_deg);
  groups.forEach((g,i)=>g.name=String(i+1));const summary=resultSummary(result);
  const p={id:uid(),name:t('result.linkName',{id:jobId.slice(0,8)}),src,width,height,groups,calibration:null,inference:{...result,jobId}};
  validateProject({schema:PROJECT_SCHEMA,pages:[p]});migrateCanonicalPaths({pages:[p]});project.pages.push(p);switchPage(p.id);changed({structural:true});
  $('model-status').textContent=t('result.loaded',{spikelets:summary.spikelet_count,awns:summary.measurement_path_count,seconds:summary.duration_seconds??'—'});
  showScale();
 }catch(e){toast(e.message);}
}
openRunLink();





let maskRenderKey='';
const candidateColor=item=>{
 if(item?.growth_stage==='seed')return '#06b6d4';
 const hop=Number(item?.hop??0);
 if(hop===1)return '#3f7bd9';
 if(hop===2)return '#7657c8';
 if(hop===3)return '#d1772f';
 if(hop===4)return '#c64e52';
 return hop>4?'#9b4aa6':'#b460bb';
};
function candidateRenderOrder(items){
 return [...items].sort((a,b)=>{
  const branchA=Number(a?.branch_index??0),branchB=Number(b?.branch_index??0);
  if(branchA!==branchB)return branchB-branchA;
  const stageA=a?.growth_stage==='seed'?-1:Number(a?.hop??0);
  const stageB=b?.growth_stage==='seed'?-1:Number(b?.hop??0);
  return stageB-stageA;
 });
}
function drawMasks(){
 const root=$('mask-layers'),current=page(),live=inferencePreview?.pageId===current?.id?inferencePreview:null;
 root.style.visibility=sourcePreviewActive()?'hidden':'visible';
 const layers=current?.inference?displayLayersFromProductResult(current.inference):(live?.layers??null);
 for(const input of document.querySelectorAll('[data-layer]')){
  const key=input.dataset.layer,items=layers?.[key];
  input.disabled=!items&&!current?.inferenceRef;
  const count=key==='candidates'&&items?new Set(items.map(item=>`${item.spikelet_id??''}:${item.branch_index??item.id}`)).size:items?.length;
  $('count-'+key).textContent=items?`(${count})`:'';
 }
 $('candidate-legend').hidden=uiState.activeDisplayLayer!=='candidates'||!layers?.candidates?.length;
 const inferenceVersion=current?.inference?.jobId??current?.inference?.source?.sha256??current?.inference?.source_sha256??(current?.inference?'loaded':'none');
 const nextMaskRenderKey=[current?.id??'',inferenceVersion,uiState.activeDisplayLayer,sourcePreviewActive(),appSettings.showSpikeletContext,live?.revision??'',live?.stage??''].join('|');
 if(nextMaskRenderKey===maskRenderKey)return;
 maskRenderKey=nextMaskRenderKey;
 root.replaceChildren();
 if(uiState.activeDisplayLayer==='edits'||!layers){
  $('layer-note').textContent=layers?t('layers.snapshotNote'):t('layers.noneNote');
  return;
 }
 const items=layers[uiState.activeDisplayLayer]??[];
 const ordered=uiState.activeDisplayLayer==='candidates'?candidateRenderOrder(items):items;
 const container=el('g',{'data-active-layer':uiState.activeDisplayLayer},root);
 if(appSettings.showSpikeletContext&&(uiState.activeDisplayLayer==='candidates'||uiState.activeDisplayLayer==='representatives')){
  const spikeletBackdrop=el('g',{'data-context-layer':'spikelet-evidence'},container);
  for(const item of (layers.raw??[]).filter(item=>Number(item.class_id)===1)){
   el('path',{d:geometryPath(item.geometry),fill:'#318368','fill-opacity':DISPLAY_OPACITY.contextSpikeletFill,'fill-rule':'evenodd',stroke:'#318368','stroke-opacity':DISPLAY_OPACITY.contextSpikeletEdge,'stroke-width':.9,'vector-effect':'non-scaling-stroke','pointer-events':'none'},spikeletBackdrop);
  }
 }
 for(const item of ordered){
  const key=uiState.activeDisplayLayer;
  const color=key==='raw'?(item.class_id===1?'#318368':'#497ddd'):key==='candidates'?candidateColor(item):'#e3a01e';
  const interactive=key==='candidates'||key==='representatives';
  const selectedMask=interactive&&uiState.selectedLayerObject?.id===String(item.id);
  const baseWidth=key==='candidates'?1.45:key==='representatives'?1.6:.8;
  const selectedWidth=key==='representatives'?3.8:3.6;
  const rawSpikelet=key==='raw'&&Number(item.class_id)===1,rawAwn=key==='raw'&&!rawSpikelet,evidenceOpacity=rawAwn?evidenceConfidenceOpacity(item):null;const fillOpacity=rawSpikelet?DISPLAY_OPACITY.rawSpikeletFill:rawAwn?evidenceOpacity:key==='candidates'?DISPLAY_OPACITY.candidateFill:DISPLAY_OPACITY.representativeFill;const strokeOpacity=selectedMask?1:rawSpikelet?DISPLAY_OPACITY.rawSpikeletEdge:rawAwn?Math.min(.55,evidenceOpacity+.10):DISPLAY_OPACITY.interactiveLine;const attrs={d:geometryPath(item.geometry),fill:color,'fill-opacity':fillOpacity,'fill-rule':'evenodd',stroke:selectedMask?'#ffffff':color,'stroke-opacity':strokeOpacity,'stroke-width':selectedMask?selectedWidth:baseWidth,'vector-effect':'non-scaling-stroke','pointer-events':interactive?'visiblePainted':'none'};
  if(interactive){
   attrs['data-mask-interactive']='true';
   attrs['data-mask-layer']=key;
   attrs['data-mask-id']=String(item.id);
   attrs['data-group']=String(item.spikelet_id??'__mask__');
   attrs['data-spikelet-id']=String(item.spikelet_id??'');
   attrs['data-branch-index']=String(item.branch_index??0);
   attrs['data-growth-stage']=String(item.growth_stage??(key==='representatives'?'representative':''));
   attrs['data-hop']=String(item.hop??0);
   attrs.style='cursor:pointer';
  }
  el('path',attrs,container);
 }
 $('layer-note').textContent=live?(live.stage==='raw'?t('layers.liveEvidence'):t('layers.liveCandidates')):t('layers.snapshotNote');
 const timings=current?.inference?timingsFromProductResult(current.inference):null;$('timing-panel').hidden=!appSettings.showDiagnostics||!timings||!Object.keys(timings).length;$('timing-details').replaceChildren();
 if(timings){for(const [key,value] of Object.entries(timings)){const row=document.createElement('p');row.textContent=`${timingLabels[key]??key}: ${value.toFixed(2)} s`;$('timing-details').appendChild(row);}const note=document.createElement('p');note.textContent=t('timing.internalNote');$('timing-details').appendChild(note);}
}
function updateMaskSelection(target){
 const root=$('mask-layers');
 for(const path of root.querySelectorAll('[data-mask-selected="true"]')){
  path.removeAttribute('data-mask-selected');
  const key=path.dataset.maskLayer,itemHop=Number(path.dataset.hop??0);
  const color=key==='candidates'?(path.dataset.growthStage==='seed'?'#06b6d4':itemHop===1?'#3f7bd9':itemHop===2?'#7657c8':itemHop===3?'#d1772f':itemHop===4?'#c64e52':itemHop>4?'#9b4aa6':'#b460bb'):'#e3a01e';
  const baseWidth=key==='candidates'?1.45:key==='representatives'?1.6:.8;
  path.setAttribute('stroke',color);path.setAttribute('stroke-opacity',String(DISPLAY_OPACITY.interactiveLine));path.setAttribute('stroke-width',String(baseWidth));
 }
 if(target){
  target.setAttribute('data-mask-selected','true');
  const selectedWidth=target.dataset.maskLayer==='representatives'?3.8:3.6;
  target.setAttribute('stroke','#ffffff');target.setAttribute('stroke-opacity','1');target.setAttribute('stroke-width',String(selectedWidth));
 }
}
function refreshLayerInspection(){
 renderWorkspaceMode();
 renderInspectionPanel();
 drawInspectionOverlay();
 for(const tr of $('rows').children)tr.classList.toggle('active',tr.getAttribute('aria-label')===t('canvas.spikeletAria',{id:group()?.name??''}));
}
$('mask-layers').addEventListener('click',e=>{
 const target=e.target.closest?.('[data-mask-interactive="true"]');
 if(!target||interaction.suppressClick)return;
 e.preventDefault();e.stopPropagation();
 const layer=target.dataset.maskLayer,maskId=target.dataset.maskId;
 let spikeletId=target.dataset.spikeletId;
 if(!spikeletId||!groupById(spikeletId)){
  if(layer==='representatives'&&page()?.inference){
   const result=normalizeProductResult(page().inference);
   spikeletId=result.measurements.find(row=>String(row.representative_awn.id)===String(maskId))?.spikelet.id??'';
  }
 }
 if(!spikeletId||!groupById(spikeletId))return;
 selected=spikeletId;selectedKind='polygon';selectedObjects=[];selectedNodes=[];node=null;tool='select';applicationState.setWorkspaceMode('inspect');
 applicationState.setInspectionBranchIndex(layer==='candidates'?Math.max(0,Number(target.dataset.branchIndex)||0):0);
 applicationState.setSelectedLayerObject({id:String(maskId),layer,spikeletId,branchIndex:uiState.inspectionBranchIndex,stage:target.dataset.growthStage,hop:Number(target.dataset.hop)||0});
 const record=inspectionRecord(),branch=inspectionBranch(),steps=branch?.hops??record?.steps??[];
 applicationState.setInspectionStep(layer==='representatives'?steps.length+(record?.representative?1:0):(target.dataset.growthStage==='seed'?0:Math.min(steps.length,Number(target.dataset.hop)||0)));
 updateMaskSelection(target);
 refreshLayerInspection();
});
const displayLayerButtons=[...document.querySelectorAll('[data-layer],#show-edits')];
function syncDisplayLayerButtons(){
 for(const button of displayLayerButtons){
  const key=button.id==='show-edits'?'edits':button.dataset.layer;
  button.setAttribute('aria-pressed',String(key===uiState.activeDisplayLayer));
 }
}
for(const button of displayLayerButtons)button.onclick=()=>perf.measureActionAsync('switch-layer',async()=>{
 const nextLayer=button.id==='show-edits'?'edits':button.dataset.layer;
 if(nextLayer!=='edits'&&isMeasurementResultPage(page())&&!page()?.inference){try{await ensureInferenceLoaded(page());}catch(error){toast(error.message);return;}}
 applicationState.setDisplayLayer(nextLayer);
 applicationState.resetInspection();
 maskRenderKey='';
 syncDisplayLayerButtons();
 draw();
});
syncDisplayLayerButtons();

// Handle drawing completion before focused buttons or rows can consume Enter.
window.addEventListener('keydown',e=>{
 if(e.key!=='Enter'||e.isComposing||!['line','polygon'].includes(tool)||document.querySelector('dialog[open]'))return;
 if(e.target.matches?.('textarea,input:not([type="range"]),select,[contenteditable="true"]'))return;
 e.preventDefault();e.stopImmediatePropagation();if(!e.repeat)finish();
},true);



