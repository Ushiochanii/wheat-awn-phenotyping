export const ONBOARDING_STORAGE_KEY='awn-studio-onboarding-v2';

export const ONBOARDING_STEPS=[
  {key:'welcome',phase:'overview',target:null,eyebrow:'Welcome to Awn Studio',title:'First, learn the workspace',body:'This guide has two parts. We will first point out the main parts of the interface, then open a sample image and walk through measurement, review, and manual correction.'},
  {key:'images',phase:'overview',target:'.images',eyebrow:'Workspace tour · Images',title:'Images live on the left',body:'Import one or many images here, move between pages, or open the bundled sample. Source images stay separate from measurement result pages so you can rerun another model later.'},
  {key:'automatic',phase:'overview',target:'.model-bar',eyebrow:'Workspace tour · Automatic measurement',title:'Choose a model and run the pipeline',body:'The model bar controls automatic measurement. Run measures the current source image, Rerun repeats the selected model, and Run pending processes source images that do not yet have a result for that model.'},
  {key:'layers',phase:'overview',target:'.layer-controls',eyebrow:'Workspace tour · Evidence',title:'Layers explain what the pipeline produced',body:'Detection evidence shows model masks, Awn candidates shows reconstructed growth hops, Representative awns shows the selected path, and Editable annotations shows the geometry you can correct.'},
  {key:'canvas',phase:'overview',target:'#canvas-wrap',eyebrow:'Workspace tour · Canvas',title:'The canvas is where review and editing happen',body:'Zoom and pan here, click a spikelet or awn to select it, and hold Ctrl to temporarily see the clean source image. Editing tools appear along the canvas edge.'},
  {key:'measurement',phase:'overview',target:'#measure-pane',eyebrow:'Workspace tour · Measurement',title:'Measurement is the final result view',body:'The table lists each spikelet, its representative awn length in millimetres, and review status. Filters help you find missing, review-suggested, edited, or verified measurements.'},
  {key:'inspect',phase:'overview',target:'.workspace-modes',eyebrow:'Workspace tour · Inspect',title:'Inspect explains how an awn was built',body:'Measure is for the final editable result. Inspect is for provenance: it shows the seed, growth hops, branches, and how the automatic Unified Growth path was assembled.'},
  {key:'project',phase:'overview',target:'.header-actions',eyebrow:'Workspace tour · Project controls',title:'Save, settings, and export stay at the top',body:'Settings controls defaults, Save project preserves the editable workspace, and Export results writes the measurements once review is complete.'},
  {key:'sample-intro',phase:'sample',target:'#demo',eyebrow:'Sample walkthrough',title:'Now run a real example',body:'The sample walkthrough uses one bundled wheat page. Open it first, then we will follow the same path you would use with your own image.',action:'open-sample',actionLabel:'Open sample image'},
  {key:'sample-scale',phase:'sample',target:'.scale-actions',eyebrow:'Sample · Scale',title:'Calibration turns pixels into millimetres',body:'For ordinary images, calibrate before measurement by drawing a line across a known distance and entering its physical length. This sample uses the printed 5 mm grid as its scale reference.'},
  {key:'sample-run',phase:'sample',target:'.model-bar',eyebrow:'Sample · Recognition',title:'Run automatic measurement',body:'This is the recognition step. The selected model detects spikelets and awn evidence, then the post-processing pipeline reconstructs fragmented awns and chooses one representative awn for each spikelet.',action:'run-sample',actionLabel:'Run automatic measurement'},
  {key:'sample-layers',phase:'sample',target:'.layer-controls',eyebrow:'Sample · Result layers',title:'Read the result from evidence to representative awn',body:'Start with Detection evidence, then Awn candidates to inspect seed and hop growth, then Representative awns. Editable annotations is the final geometry used for measurement.'},
  {key:'sample-table',phase:'sample',target:'#measure-pane',eyebrow:'Sample · Measurements',title:'What to read in Measurement',body:'ID identifies the spikelet. Awn length is the calibrated representative-path length in millimetres. Status tells you whether the result is high-confidence, suggested for review, missing, edited, or verified.'},
  {key:'sample-inspect',phase:'sample',target:'.workspace-modes',eyebrow:'Sample · Inspect',title:'Use Inspect when a result looks suspicious',body:'Select one spikelet, open Inspect, and step through Seed and Growth hops. This is where you can see whether a long awn came from continuous evidence or from a questionable bridge.',action:'inspect',actionLabel:'Open Inspect'},
  {key:'edit-select',phase:'edit',target:'#measure-editor',fallback:'#canvas-wrap',eyebrow:'Manual correction · Select',title:'Select the object you want to correct',body:'Return to Measure and click a spikelet or representative awn on the canvas. The selected item is linked to the Measurement panel, so you can focus it and see its current length.',action:'measure',actionLabel:'Back to Measure'},
  {key:'edit-vertices',phase:'edit',target:'#canvas-wrap',eyebrow:'Manual correction · Vertices',title:'Drag, add, or delete path vertices',body:'Drag a vertex to refine the path. Click an awn path to insert a new vertex. Select a vertex and press Delete to remove it. These edits update the representative path and its measured length.'},
  {key:'edit-box',phase:'edit',target:'#canvas-tools',eyebrow:'Manual correction · Box select',title:'Clean several bad vertices at once',body:'Use Box selection (B) to drag a rectangle around multiple vertices or objects, then Delete. This is useful for removing a false branch or a group of misplaced points in one operation.'},
  {key:'edit-redraw',phase:'edit',target:'#canvas-tools',eyebrow:'Manual correction · Replace',title:'Redraw a representative awn when the path is wrong',body:'Use Redraw representative awn (L) when local vertex edits are not enough. Draw the biologically correct path from the spikelet base to the awn tip and finish with Enter.'},
  {key:'edit-add-delete',phase:'edit',target:'#canvas-tools',eyebrow:'Manual correction · Missing or false objects',title:'Add missed spikelets and delete false detections',body:'Use Add spikelet (P) for a missed spikelet. Select a false spikelet, awn path, or vertices and use Delete to remove them. Undo and Redo remain available throughout correction.'},
  {key:'export',phase:'finish',target:'#export',eyebrow:'Finish',title:'Export after review',body:'When the measurements look correct, export the current image or the full project. You can reopen the tutorial at any time from the ? button.'},
];

const $=id=>document.getElementById(id);
let stepIndex=0;
let running=false;
let repositionTimer=0;

function visibleTarget(step){
  const candidates=[step.target,step.fallback].filter(Boolean);
  for(const selector of candidates){
    const node=document.querySelector(selector);
    if(!node)continue;
    const rect=node.getBoundingClientRect();
    const style=getComputedStyle(node);
    if(rect.width>1&&rect.height>1&&style.display!=='none'&&style.visibility!=='hidden')return node;
  }
  return null;
}

function ensureUI(){
  if($('onboarding-root'))return;
  const root=document.createElement('div');
  root.id='onboarding-root';root.hidden=true;
  root.innerHTML=`
    <div class="onboarding-shade" aria-hidden="true"></div>
    <div class="onboarding-spotlight" aria-hidden="true"></div>
    <section class="onboarding-card" role="dialog" aria-modal="true" aria-labelledby="onboarding-title" aria-describedby="onboarding-body">
      <div class="onboarding-card-top"><span id="onboarding-eyebrow" class="onboarding-eyebrow"></span><button id="onboarding-close" class="onboarding-close" type="button" aria-label="Close tutorial">×</button></div>
      <h2 id="onboarding-title"></h2><p id="onboarding-body"></p>
      <button id="onboarding-action" class="onboarding-action" type="button" hidden></button>
      <div class="onboarding-footer"><button id="onboarding-skip" type="button">Skip tutorial</button><span id="onboarding-progress" aria-label="Tutorial progress"></span><div class="onboarding-nav"><button id="onboarding-back" type="button">Back</button><button id="onboarding-next" class="primary" type="button">Start tour</button></div></div>
    </section>`;
  document.body.append(root);
  $('onboarding-close').onclick=closeTour;
  $('onboarding-skip').onclick=closeTour;
  $('onboarding-back').onclick=()=>showStep(stepIndex-1);
  $('onboarding-next').onclick=()=>stepIndex>=ONBOARDING_STEPS.length-1?closeTour():showStep(stepIndex+1);
  $('onboarding-action').onclick=runStepAction;
}

function setSeen(){try{localStorage.setItem(ONBOARDING_STORAGE_KEY,'seen');}catch{}}
function hasSeen(){try{return localStorage.getItem(ONBOARDING_STORAGE_KEY)==='seen';}catch{return false;}}

function positionCard(target){
  const root=$('onboarding-root');if(!root||root.hidden)return;
  const card=root.querySelector('.onboarding-card'),spotlight=root.querySelector('.onboarding-spotlight'),shade=root.querySelector('.onboarding-shade');
  spotlight.hidden=!target;shade.hidden=Boolean(target);
  if(!target){spotlight.style.cssText='';card.dataset.placement='center';card.style.left='50%';card.style.top='50%';card.style.transform='translate(-50%,-50%)';return;}
  const rect=target.getBoundingClientRect(),pad=7;
  spotlight.style.left=`${Math.max(5,rect.left-pad)}px`;spotlight.style.top=`${Math.max(5,rect.top-pad)}px`;spotlight.style.width=`${Math.min(innerWidth-10,rect.width+pad*2)}px`;spotlight.style.height=`${Math.min(innerHeight-10,rect.height+pad*2)}px`;
  card.style.transform='none';
  const cardWidth=Math.min(410,innerWidth-28),gap=14;
  let left=rect.right+gap,top=Math.max(14,Math.min(rect.top,innerHeight-390)),placement='right';
  if(innerWidth<760){left=Math.max(14,(innerWidth-cardWidth)/2);top=Math.max(14,innerHeight-340);placement='bottom';}
  else if(left+cardWidth>innerWidth-14&&rect.left-cardWidth-gap>=14){left=rect.left-cardWidth-gap;placement='left';}
  else if(left+cardWidth>innerWidth-14){left=Math.max(14,(innerWidth-cardWidth)/2);top=rect.bottom+gap;placement='bottom';if(top+340>innerHeight-14)top=Math.max(14,rect.top-340-gap);}
  card.dataset.placement=placement;card.style.left=`${left}px`;card.style.top=`${top}px`;
}
function schedulePosition(target){clearTimeout(repositionTimer);repositionTimer=setTimeout(()=>positionCard(target),180);}
function phaseLabel(step){return step.phase==='overview'?'Interface':step.phase==='sample'?'Sample':step.phase==='edit'?'Editing':'Finish';}

function showStep(index){
  if(!running)return;
  stepIndex=Math.max(0,Math.min(index,ONBOARDING_STEPS.length-1));
  const step=ONBOARDING_STEPS[stepIndex],action=$('onboarding-action');
  $('onboarding-eyebrow').textContent=step.eyebrow;$('onboarding-title').textContent=step.title;$('onboarding-body').textContent=step.body;
  action.hidden=!step.action;action.textContent=step.actionLabel||'Try it';action.disabled=false;
  $('onboarding-back').hidden=stepIndex===0;$('onboarding-next').textContent=stepIndex===0?'Start tour':stepIndex===ONBOARDING_STEPS.length-1?'Finish':'Next';
  $('onboarding-progress').textContent=`${phaseLabel(step)} · ${stepIndex+1} / ${ONBOARDING_STEPS.length}`;
  const target=visibleTarget(step);
  if(target){positionCard(target);target.scrollIntoView({block:'center',inline:'nearest',behavior:'smooth'});schedulePosition(target);}else positionCard(null);
  requestAnimationFrame(()=>$('onboarding-next')?.focus({preventScroll:true}));
}

async function runStepAction(){
  const step=ONBOARDING_STEPS[stepIndex],button=$('onboarding-action');if(!step?.action)return;
  button.disabled=true;
  if(step.action==='open-sample'){
    const before=Number($('image-count')?.textContent||0);
    button.textContent='Opening sample…';$('demo')?.click();
    for(let i=0;i<60;i++){await new Promise(resolve=>setTimeout(resolve,100));if(Number($('image-count')?.textContent||0)>before)break;}
    const calibrationDialog=$('scale-dialog');if(calibrationDialog?.open)calibrationDialog.close();
    showStep(stepIndex+1);return;
  }
  if(step.action==='run-sample'){
    const run=$('run-model');
    if(!run||run.disabled){button.textContent='Model is not ready yet';button.disabled=false;return;}
    button.textContent='Measuring…';run.click();
    for(let i=0;i<1800;i++){await new Promise(resolve=>setTimeout(resolve,100));if(Number(($('group-count')?.textContent||'0').match(/\\d+/)?.[0]||0)>0){showStep(stepIndex+1);return;}}
    button.textContent='Run automatic measurement';button.disabled=false;return;
  }
  if(step.action==='inspect'){document.querySelector('[data-workspace-mode="inspect"]')?.click();showStep(stepIndex);}
  else if(step.action==='measure'){document.querySelector('[data-workspace-mode="measure"]')?.click();showStep(stepIndex);}
  button.disabled=false;
}

export function startTour({markSeen=true}={}){
  ensureUI();if(running)return;running=true;if(markSeen)setSeen();$('onboarding-root').hidden=false;document.body.classList.add('onboarding-active');showStep(0);
}
export function closeTour(){
  if(!running)return;running=false;const root=$('onboarding-root');if(root)root.hidden=true;document.body.classList.remove('onboarding-active');clearTimeout(repositionTimer);$('how-to-start')?.focus({preventScroll:true});
}
export function initOnboarding(){
  ensureUI();$('how-to-start')?.addEventListener('click',()=>startTour({markSeen:true}));
  addEventListener('resize',()=>running&&positionCard(visibleTarget(ONBOARDING_STEPS[stepIndex])));
  addEventListener('scroll',()=>running&&positionCard(visibleTarget(ONBOARDING_STEPS[stepIndex])),true);
  addEventListener('keydown',event=>{if(!running)return;if(event.key==='Escape'){event.preventDefault();closeTour();}else if(event.key==='ArrowRight'){event.preventDefault();stepIndex>=ONBOARDING_STEPS.length-1?closeTour():showStep(stepIndex+1);}else if(event.key==='ArrowLeft'&&stepIndex>0){event.preventDefault();showStep(stepIndex-1);}});
  if(!hasSeen())setTimeout(()=>startTour({markSeen:true}),650);
}
