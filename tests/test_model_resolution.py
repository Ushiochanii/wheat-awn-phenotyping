import hashlib
import sys
import types
from pathlib import Path

import awnphen.model as model


def test_canonical_blob_is_materialized_with_pt_suffix(tmp_path, monkeypatch):
    payload = b"canonical-weights"
    blob = tmp_path / hashlib.sha256(payload).hexdigest()
    blob.write_bytes(payload)

    monkeypatch.setattr(model, "HF_MODEL_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(model, "CANONICAL_MODEL_DIR", tmp_path / "materialized")

    fake_hf = types.SimpleNamespace(
        hf_hub_download=lambda **_: str(blob)
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hf)

    resolved = model.resolve_weights()

    assert resolved.name == "best.pt"
    assert resolved.suffix == ".pt"
    assert resolved.read_bytes() == payload
