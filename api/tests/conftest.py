
import os
import shutil
import pytest
from app import config

@pytest.fixture(scope="session", autouse=True)
def global_test_env():
    """Ensure a safe data dir exists for tests that use the default config."""
    # Use a persistent temp dir for the session
    session_data_dir = os.path.abspath("./test_data_session")
    os.environ["FLOW_DATA_DIR"] = session_data_dir
    os.makedirs(session_data_dir, exist_ok=True)

    # Ensure config picks this up
    config.clear_config_cache()

    yield

    # Cleanup after session
    if os.path.exists(session_data_dir):
        shutil.rmtree(session_data_dir)
