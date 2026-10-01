const SVG_NS = 'http://www.w3.org/2000/svg';

function svgElement(name, attrs, parent) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
  parent.appendChild(element);
  return element;
}

const inspectionColors = ['#06b6d4','#497ddd','#8c6ac8','#c9792b','#b85d83','#477f89','#8f7a32'];

export function renderInspectionOverlay({
  root,
  record,
  branch,
  workspaceMode,
  ctrl,
  displayLayer,
  inspectionStep,
  inspectionBranchIndex,
  showPool = false
}) {
  root.replaceChildren();
  const visible =
    workspaceMode === 'inspect' &&
    !ctrl &&
    record &&
    (displayLayer === 'candidates' || displayLayer === 'representatives');

  root.style.visibility = visible ? 'visible' : 'hidden';
  if (!visible) return;

  const path = (points, stroke, width, dash = '') => {
    if (!points?.length || points.length < 2) return;
    const attrs = {
      points: points.map(point => point.join(',')).join(' '),
      fill: 'none',
      stroke,
      'stroke-width': width,
      'vector-effect': 'non-scaling-stroke',
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round'
    };
    if (dash) attrs['stroke-dasharray'] = dash;
    svgElement('polyline', attrs, root);
  };

  if (showPool) {
    for (const support of record.related_supports ?? []) {
      path(support.raw_path, '#89938d', 1.3, '4 3');
    }
  }

  const seed = branch?.seed?.raw_path ?? record.winner_seed?.raw_path ?? [];
  path(seed, inspectionColors[0], 4);

  const steps = branch?.hops ?? record.steps ?? [];
  const visibleHops = Math.min(inspectionStep, steps.length);
  for (let index = 0; index < visibleHops; index++) {
    path(steps[index].raw_path, inspectionColors[(index + 1) % inspectionColors.length], 3.4);
  }

  if (inspectionStep > steps.length && inspectionBranchIndex === 0) {
    path(
      record.representative?.raw_path ?? record.winner?.final_raw_path ?? [],
      '#d18d18',
      5
    );
  }
}

export function updateEditableGeometry({root, group, screenScale}) {
  if (!root || !group) return;
  const id = CSS.escape(group.uid);
  const polygon = root.querySelector(`polygon[data-group="${id}"][data-kind="polygon"]`);
  if (polygon) {
    polygon.setAttribute('points', group.polygon.map(point => point.join(',')).join(' '));
  }
  for (const line of root.querySelectorAll(`polyline[data-group="${id}"][data-kind="line"]`)) {
    line.setAttribute('points', group.line.map(point => point.join(',')).join(' '));
  }
  const label = root.querySelector(`text[data-group="${id}"]`);
  if (label && group.polygon.length) {
    const anchor = group.polygon.reduce(
      (current, point) => point[1] > current[1] ? point : current,
      group.polygon[0]
    );
    label.setAttribute('x', anchor[0] + 7 / screenScale);
    label.setAttribute('y', anchor[1] + 14 / screenScale);
  }
}

export function updateMarqueeRect({root, marquee}) {
  if (!root || !marquee) return;
  const rect = root.querySelector('rect.marquee');
  if (!rect) return;
  const x = Math.min(marquee[0][0], marquee[1][0]);
  const y = Math.min(marquee[0][1], marquee[1][1]);
  rect.setAttribute('x', x);
  rect.setAttribute('y', y);
  rect.setAttribute('width', Math.abs(marquee[1][0] - marquee[0][0]));
  rect.setAttribute('height', Math.abs(marquee[1][1] - marquee[0][1]));
}

export function updateEditableNodePosition({root, groupId, kind, index, point}) {
  if (!root || !groupId || !point) return;
  const id = CSS.escape(groupId);
  for (const circle of root.querySelectorAll(
    `circle.node[data-group="${id}"][data-kind="${kind}"][data-index="${index}"]`
  )) {
    circle.setAttribute('cx', point[0]);
    circle.setAttribute('cy', point[1]);
  }
}

export function renderEditableAnnotations({
  root,
  draftRoot,
  page,
  editsVisible,
  screenScale,
  workspaceMode,
  tool,
  objectSelected,
  nodeSelected,
  selectedNode,
  hiddenLineGroupId,
  scaleDraft,
  draft,
  marquee
}) {
  root.replaceChildren();
  draftRoot.replaceChildren();

  root.style.visibility = editsVisible ? 'visible' : 'hidden';
  root.style.pointerEvents = editsVisible ? 'auto' : 'none';
  draftRoot.style.visibility = editsVisible ? 'visible' : 'hidden';

  if (!page || !editsVisible) return;

  const radius = 7 / screenScale;

  for (const group of page.groups) {
    const polygonChosen = objectSelected(group.uid, 'polygon');
    const lineChosen = objectSelected(group.uid, 'line');

    svgElement('polygon', {
      points: group.polygon.map(point => point.join(',')).join(' '),
      fill: polygonChosen ? '#44896430' : '#44896415',
      stroke: polygonChosen ? '#225d40' : '#4c8d66',
      'stroke-width': polygonChosen ? 2 : 1,
      'vector-effect': 'non-scaling-stroke',
      class: 'shape',
      'data-group': group.uid,
      'data-kind': 'polygon'
    }, root);

    if (group.line.length > 1 && group.uid !== hiddenLineGroupId) {
      const attrs = {
        points: group.line.map(point => point.join(',')).join(' '),
        fill: 'none',
        'vector-effect': 'non-scaling-stroke',
        class: 'shape',
        'data-group': group.uid,
        'data-kind': 'line'
      };
      svgElement('polyline', {
        ...attrs,
        stroke: 'transparent',
        'stroke-width': 20,
        'pointer-events': 'stroke',
        'data-hit': 'line'
      }, root);
      svgElement('polyline', {
        ...attrs,
        stroke: lineChosen ? '#d18d18' : '#d4a33d',
        'stroke-width': lineChosen ? 4 : 2.5,
        'pointer-events': 'none'
      }, root);
    }

    const anchor = group.polygon.reduce(
      (current, point) => point[1] > current[1] ? point : current,
      group.polygon[0]
    );
    const label = svgElement('text', {
      x: anchor[0] + 7 / screenScale,
      y: anchor[1] + 14 / screenScale,
      'font-size': 12 / screenScale,
      fill: '#183d2a',
      stroke: 'white',
      'stroke-width': 3 / screenScale,
      'paint-order': 'stroke',
      'font-weight': 600,
      'data-group': group.uid,
      class: 'shape'
    }, root);
    label.textContent = group.name;

    if (workspaceMode === 'measure' && (tool === 'select' || tool === 'box')) {
      for (const kind of ['polygon', 'line']) {
        if (!objectSelected(group.uid, kind)) continue;
        group[kind].forEach((point, index) => {
          const attrs = {
            cx: point[0],
            cy: point[1],
            class: 'node',
            'data-group': group.uid,
            'data-kind': kind,
            'data-index': index
          };
          svgElement('circle', {
            ...attrs,
            r: 13 / screenScale,
            fill: 'transparent',
            'pointer-events': 'all',
            'data-hit': 'node'
          }, root);
          svgElement('circle', {
            ...attrs,
            r: radius,
            fill:
              nodeSelected(group.uid, kind, index) ||
              (
                selectedNode?.uid === group.uid &&
                selectedNode.kind === kind &&
                selectedNode.index === index
              )
                ? '#d18d18'
                : 'white',
            stroke: kind === 'line' ? '#c38722' : '#245c48',
            'stroke-width': 2,
            'vector-effect': 'non-scaling-stroke',
            'pointer-events': 'none'
          }, root);
        });
      }
    }
  }

  const scalePoints = scaleDraft ?? page.calibration?.points;
  if (scalePoints?.length === 2) {
    svgElement('polyline', {
      points: scalePoints.map(point => point.join(',')).join(' '),
      stroke: '#4d7db2',
      'stroke-width': 2,
      'stroke-dasharray': '5 3',
      'vector-effect': 'non-scaling-stroke',
      fill: 'none'
    }, root);
  }

  if (draft.length) {
    svgElement('polyline', {
      points: draft.map(point => point.join(',')).join(' '),
      fill: tool === 'polygon' ? '#44896420' : 'none',
      stroke: '#245c48',
      'stroke-width': 2,
      'vector-effect': 'non-scaling-stroke'
    }, draftRoot);
    for (const point of draft) {
      svgElement('circle', {
        cx: point[0],
        cy: point[1],
        r: tool === 'scale' ? 5 / screenScale : radius,
        fill: '#245c48'
      }, draftRoot);
    }
  }

  if (marquee) {
    const x = Math.min(marquee[0][0], marquee[1][0]);
    const y = Math.min(marquee[0][1], marquee[1][1]);
    svgElement('rect', {
      x,
      y,
      width: Math.abs(marquee[1][0] - marquee[0][0]),
      height: Math.abs(marquee[1][1] - marquee[0][1]),
      class: 'marquee'
    }, draftRoot);
  }
}
