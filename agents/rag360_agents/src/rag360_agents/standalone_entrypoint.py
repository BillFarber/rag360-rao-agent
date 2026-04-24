"""Custom entrypoint that injects BearerTokenMiddleware before starting arag-standalone.

Run with: python -m rag360_agents.standalone_entrypoint

The monkey-patch is applied during StandaloneApplication.__init__, before the
middleware stack is built (which happens on the first ASGI call). This is the
only hook available without modifying the RAO base image.
"""
from nuclia_arag_standalone.app import StandaloneApplication

from rag360_agents.auth_middleware import BearerTokenMiddleware

_original_init = StandaloneApplication.__init__


def _patched_init(self, *args, **kwargs):
    _original_init(self, *args, **kwargs)
    self.add_middleware(BearerTokenMiddleware)


StandaloneApplication.__init__ = _patched_init

from nuclia_arag_standalone.run import run  # noqa: E402

run()
