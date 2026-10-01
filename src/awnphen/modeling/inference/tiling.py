"""Sliding-window tiling shared by training and frozen inference."""

from __future__ import annotations

import hashlib

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def starts(length, size=640, stride=320):
    """Same schedule for training and inference; shift final window to image edge."""
    if not 0 < stride <= size:
        raise ValueError('Require 0 < stride <= size')
    return sorted(set([*range(0, max(1, length-size+1), stride), max(0, length-size)]))


def windows(width, height, size=640, stride=320):
    return [(x,y,min(x+size,width),min(y+size,height))
            for y in starts(height,size,stride) for x in starts(width,size,stride)]

__all__ = ["sha", "starts", "windows"]
