"""Pipeline node helpers (ARCHITECTURE.md §4, §5, §6, WS2).

Split out of ``graph/pipeline.py`` to keep every file well under the 800-line
limit. ``builders`` holds the pure mappers (internal DTO -> wire model);
``stages`` holds the staged async generator both ``run_analysis`` and the SSE
stream consume.
"""

from __future__ import annotations
