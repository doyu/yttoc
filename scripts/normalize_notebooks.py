#!/usr/bin/env python3
"""Normalize notebook source fields to list-of-strings format.

Usage:
    scripts/normalize_notebooks.py nb1.ipynb nb2.ipynb ...
"""
import sys, nbformat

notebooks = [f for f in sys.argv[1:] if f.endswith(".ipynb")]
if not notebooks:
    sys.exit(0)

def rstrip_source(nb):
    """Remove trailing whitespace from each line in cell source."""
    for cell in nb.cells:
        src = cell.get("source", "")
        if isinstance(src, list):
            cell["source"] = [l.rstrip() + "\n" if l.endswith("\n") else l.rstrip() for l in src]
        elif isinstance(src, str):
            cell["source"] = "\n".join(l.rstrip() for l in src.split("\n"))

for path in notebooks:
    nb = nbformat.read(path, as_version=4)
    rstrip_source(nb)
    nbformat.write(nb, path)
    print(f"normalized: {path}")
