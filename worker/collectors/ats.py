"""Registry of supported ATS collectors."""

from worker.collectors import ashby, comeet, greenhouse, lever

COLLECTORS = {m.ATS: m for m in (greenhouse, lever, ashby, comeet)}
SUPPORTED = set(COLLECTORS)
