import test from 'node:test';
import assert from 'node:assert/strict';
import {createHistoryManager} from '../../app/awn_studio/history_manager.mjs';

test('history manager preserves undo/redo semantics and clears redo on checkpoint', () => {
  const history = createHistoryManager({limit: 3});
  history.checkpoint({value: 1});
  history.checkpoint({value: 2});

  assert.equal(history.canUndo, true);
  assert.equal(history.undo({value: 3}).value, 2);
  assert.equal(history.canRedo, true);
  assert.equal(history.redo({value: 2}).value, 3);

  history.undo({value: 3});
  history.checkpoint({value: 9});
  assert.equal(history.canRedo, false);
});

test('history manager enforces its configured limit', () => {
  const history = createHistoryManager({limit: 2});
  history.checkpoint({value: 1});
  history.checkpoint({value: 2});
  history.checkpoint({value: 3});
  assert.equal(history.sizes().past, 2);
  assert.equal(history.undo({value: 4}).value, 3);
  assert.equal(history.undo({value: 3}).value, 2);
  assert.equal(history.canUndo, false);
});
