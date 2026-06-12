"""Core infrastructure: settings, CORS, rate limiting, and logging.

These modules are environment-driven and secret-safe (no hardcoded
credentials). See ARCHITECTURE.md §11.3.
"""

from __future__ import annotations
