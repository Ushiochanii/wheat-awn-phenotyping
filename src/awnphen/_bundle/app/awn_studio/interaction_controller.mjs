export function createInteractionController() {
  let mode = 'idle';
  let payload = null;
  let space = false;
  let ctrl = false;
  let suppressClick = false;

  function begin(nextMode, nextPayload = null) {
    if (!['pan', 'drag-node', 'box'].includes(nextMode)) {
      throw new Error(`Unsupported interaction mode: ${nextMode}`);
    }
    mode = nextMode;
    payload = nextPayload;
    return payload;
  }

  function end() {
    const previous = {mode, payload};
    mode = 'idle';
    payload = null;
    return previous;
  }

  function resetTransient() {
    const previous = end();
    space = false;
    ctrl = false;
    suppressClick = false;
    return previous;
  }

  return Object.freeze({
    begin,
    end,
    resetTransient,
    setSpace(value) {
      space = Boolean(value);
    },
    setCtrl(value) {
      ctrl = Boolean(value);
    },
    suppressNextClick() {
      suppressClick = true;
    },
    releaseClickSuppression() {
      suppressClick = false;
    },
    get mode() {
      return mode;
    },
    get payload() {
      return payload;
    },
    get space() {
      return space;
    },
    get ctrl() {
      return ctrl;
    },
    get suppressClick() {
      return suppressClick;
    },
    get active() {
      return mode !== 'idle';
    }
  });
}
