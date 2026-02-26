
import os
import shutil
import json
import logging
import pytest
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.outputs import LLMResult, Generation
from app import logging_conf, config

TEST_DATA_DIR = os.path.abspath("./test_data_logging_unit")

@pytest.fixture
def setup_logging_test_env():
    # Save original env
    original_data_dir = os.environ.get("FLOW_DATA_DIR")

    # Setup isolated env
    os.environ["FLOW_DATA_DIR"] = TEST_DATA_DIR
    os.environ["LOG_LEVEL"] = "DEBUG"
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)
    config.clear_config_cache()

    # Reconfigure logging for this test
    # First clear existing handlers (from session/conftest) to avoid noise/conflicts
    logging.getLogger().handlers = []
    logging_conf.configure_logging()

    yield

    # Teardown
    # 1. Close and remove all handlers created during this test
    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        h.close()
        root_logger.removeHandler(h)

    # 2. Clean up dir
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)

    # 3. Restore env
    if original_data_dir:
        os.environ["FLOW_DATA_DIR"] = original_data_dir
    else:
        del os.environ["FLOW_DATA_DIR"]
    config.clear_config_cache()

    # 4. Restore session logging (so subsequent tests work)
    # We assume conftest.py sets FLOW_DATA_DIR to session dir
    logging_conf.configure_logging()

def test_configure_logging_creates_app_log(setup_logging_test_env):
    logger = logging.getLogger("test_logger")
    logger.info("Test log message")

    app_log = os.path.join(TEST_DATA_DIR, "app.log")
    assert os.path.exists(app_log)

    with open(app_log, "r") as f:
        content = f.read()
        assert "Test log message" in content

def test_llm_logging_callback_handler(setup_logging_test_env):
    handler = logging_conf.LLMLoggingCallbackHandler()

    # Test Start
    messages = [[SystemMessage(content="Sys"), HumanMessage(content="Human")]]
    handler.on_chat_model_start({"name": "gpt-4"}, messages)

    # Test End
    response = LLMResult(
        generations=[[Generation(text="Response")]],
        llm_output={"token_usage": 10}
    )
    handler.on_llm_end(response)

    # Test Error
    handler.on_llm_error(ValueError("Test Error"))

    llm_log = os.path.join(TEST_DATA_DIR, "llm_interactions.log")
    assert os.path.exists(llm_log)

    with open(llm_log, "r") as f:
        lines = f.readlines()
        assert len(lines) == 3

        start_entry = json.loads(lines[0])
        assert start_entry["event"] == "start"
        assert start_entry["model"] == "gpt-4"
        assert len(start_entry["input_messages"]) == 2

        end_entry = json.loads(lines[1])
        assert end_entry["event"] == "end"
        assert end_entry["output_generations"] == ["Response"]

        error_entry = json.loads(lines[2])
        assert error_entry["event"] == "error"
        assert error_entry["error"] == "Test Error"
