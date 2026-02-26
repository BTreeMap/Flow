"""Centralized logging configuration and observability tools."""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
from datetime import UTC, datetime
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from app import config


def configure_logging() -> None:
    """Configure logging for the application.

    Sets up:
    1. Console logging (stdout) with human-readable format.
    2. File logging (app.log) in the data directory.
    """
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    data_dir = config.get_data_dir()
    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError as e:
        # Fallback if we can't create data dir (e.g. permission issues in dev)
        print(f"Failed to create data directory {data_dir}: {e}")

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # clear existing handlers to avoid duplicates if re-configured
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # 1. Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # 2. File Handler (app.log)
    app_log_path = os.path.join(data_dir, "app.log")
    try:
        file_handler = logging.handlers.WatchedFileHandler(app_log_path)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging to {app_log_path}: {e}")

    # Set some noisy libraries to WARNING
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class LLMLoggingCallbackHandler(BaseCallbackHandler):
    """Callback handler for logging LLM interactions to file and logger."""

    def __init__(self) -> None:
        super().__init__()
        data_dir = config.get_data_dir()
        self.log_path = os.path.join(data_dir, "llm_interactions.log")
        # Ensure directory exists
        os.makedirs(data_dir, exist_ok=True)
        self.logger = logging.getLogger(__name__)

    def _write_log(self, entry: dict[str, Any]) -> None:
        """Write a JSON log entry to the file."""
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            self.logger.exception("Failed to write to LLM log file")

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        **kwargs: Any,
    ) -> None:
        """Run when LLM starts running."""
        model = serialized.get("name") or serialized.get("id") or "unknown"
        timestamp = datetime.now(UTC).isoformat()

        # Flatten messages for logging if multiple generations
        # Usually messages is [[System, User]] for a single generation
        flat_messages = []
        for batch in messages:
            for msg in batch:
                flat_messages.append({"role": msg.type, "content": msg.content})

        entry = {
            "timestamp": timestamp,
            "event": "start",
            "model": model,
            "input_messages": flat_messages,
        }

        self.logger.info(f"LLM request started: {model}")
        self.logger.debug(f"LLM input: {json.dumps(entry, default=str)}")
        self._write_log(entry)

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Run when LLM ends running."""
        timestamp = datetime.now(UTC).isoformat()

        generations = []
        for gen_list in response.generations:
            for gen in gen_list:
                generations.append(gen.text)

        entry = {
            "timestamp": timestamp,
            "event": "end",
            "output_generations": generations,
            "llm_output": response.llm_output,  # Token usage often here
        }

        self.logger.info("LLM request finished")
        self.logger.debug(f"LLM output: {json.dumps(entry, default=str)}")
        self._write_log(entry)

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        """Run when LLM errors."""
        timestamp = datetime.now(UTC).isoformat()
        entry = {
            "timestamp": timestamp,
            "event": "error",
            "error": str(error),
        }
        self.logger.error(f"LLM error: {error}")
        self._write_log(entry)
