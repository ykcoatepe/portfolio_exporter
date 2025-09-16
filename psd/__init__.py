"""Lightweight import shim to access in-repo `src.psd` package as `psd`.

This keeps imports like `from psd.runner import start_psd` working without
installing a separate distribution for PSD.
"""

