"""
Shared pytest fixtures for the Cloudway test suite.

Unit tests use MockLLM (zero cost, zero Bedrock calls).
Integration/E2E tests (test_pipeline_real.py) use real Bedrock and are
skipped automatically unless RUN_REAL_LLM=true is set in the environment.
"""

import os
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_llm: mark test as requiring live Bedrock credentials (skipped by default)",
    )


@pytest.fixture(autouse=True)
def skip_real_llm(request):
    if request.node.get_closest_marker("real_llm"):
        if os.getenv("RUN_REAL_LLM", "false").lower() != "true":
            pytest.skip("set RUN_REAL_LLM=true to run Bedrock integration tests")
