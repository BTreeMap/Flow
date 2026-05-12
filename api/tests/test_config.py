import pytest
from app import config


@pytest.fixture(autouse=True)
def clear_cache():
    config.clear_config_cache()
    yield
    config.clear_config_cache()


def test_get_vapid_public_key(monkeypatch):
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("FLOW_VAPID_PUBLIC_KEY", raising=False)
    assert config.get_vapid_public_key() == ""

    monkeypatch.setenv("VAPID_PUBLIC_KEY", "test_pub")
    config.clear_config_cache()
    assert config.get_vapid_public_key() == "test_pub"

    monkeypatch.delenv("VAPID_PUBLIC_KEY")
    monkeypatch.setenv("FLOW_VAPID_PUBLIC_KEY", "flow_pub")
    config.clear_config_cache()
    assert config.get_vapid_public_key() == "flow_pub"


def test_get_vapid_private_key(monkeypatch):
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("FLOW_VAPID_PRIVATE_KEY", raising=False)
    assert config.get_vapid_private_key() == ""

    monkeypatch.setenv("VAPID_PRIVATE_KEY", "test_priv")
    config.clear_config_cache()
    assert config.get_vapid_private_key() == "test_priv"

    monkeypatch.delenv("VAPID_PRIVATE_KEY")
    monkeypatch.setenv("FLOW_VAPID_PRIVATE_KEY", "flow_priv")
    config.clear_config_cache()
    assert config.get_vapid_private_key() == "flow_priv"


def test_get_vapid_sub(monkeypatch):
    monkeypatch.delenv("VAPID_CLAIM_SUB", raising=False)
    assert config.get_vapid_sub() == "mailto:flow@oss.joefang.org"

    monkeypatch.setenv("VAPID_CLAIM_SUB", "mailto:test@example.com")
    config.clear_config_cache()
    assert config.get_vapid_sub() == "mailto:test@example.com"


def test_get_push_gone_410_threshold_default(monkeypatch):
    monkeypatch.delenv("FLOW_PUSH_GONE_410_THRESHOLD", raising=False)
    assert config.get_push_gone_410_threshold() == 2


def test_get_push_gone_410_threshold_custom(monkeypatch):
    monkeypatch.setenv("FLOW_PUSH_GONE_410_THRESHOLD", "5")
    config.clear_config_cache()
    assert config.get_push_gone_410_threshold() == 5


def test_get_push_gone_410_threshold_invalid(monkeypatch):
    monkeypatch.setenv("FLOW_PUSH_GONE_410_THRESHOLD", "not_a_number")
    config.clear_config_cache()
    assert config.get_push_gone_410_threshold() == 2


def test_get_port(monkeypatch):
    monkeypatch.delenv("API_PORT", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    assert config.get_port() == 8000

    monkeypatch.setenv("PORT", "9001")
    config.clear_config_cache()
    assert config.get_port() == 9001

    monkeypatch.setenv("API_PORT", "9000")
    config.clear_config_cache()
    assert config.get_port() == 9000

    monkeypatch.setenv("API_PORT", "invalid")
    config.clear_config_cache()
    assert config.get_port() == 8000


def test_get_log_level(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert config.get_log_level() == "INFO"

    monkeypatch.setenv("LOG_LEVEL", "debug")
    config.clear_config_cache()
    assert config.get_log_level() == "DEBUG"


def test_feedback_loop_enabled_default_and_override(monkeypatch):
    monkeypatch.delenv("ENABLE_AUTOMATED_FEEDBACK", raising=False)
    assert config.is_feedback_loop_enabled() is True

    monkeypatch.setenv("ENABLE_AUTOMATED_FEEDBACK", "false")
    config.clear_config_cache()
    assert config.is_feedback_loop_enabled() is False


def test_feedback_delay_minutes(monkeypatch):
    monkeypatch.delenv("FEEDBACK_DELAY_MINUTES", raising=False)
    assert config.get_feedback_delay_minutes() == 120

    monkeypatch.setenv("FEEDBACK_DELAY_MINUTES", "45")
    config.clear_config_cache()
    assert config.get_feedback_delay_minutes() == 45

    monkeypatch.setenv("FEEDBACK_DELAY_MINUTES", "0")
    config.clear_config_cache()
    assert config.get_feedback_delay_minutes() == 1

    monkeypatch.setenv("FEEDBACK_DELAY_MINUTES", "invalid")
    config.clear_config_cache()
    assert config.get_feedback_delay_minutes() == 120


def test_feedback_prompt_text(monkeypatch):
    monkeypatch.delenv("FEEDBACK_PROMPT_TEXT", raising=False)
    assert config.get_feedback_prompt_text() == "How did this prompt work for you?"

    monkeypatch.setenv("FEEDBACK_PROMPT_TEXT", "Did this help?")
    config.clear_config_cache()
    assert config.get_feedback_prompt_text() == "Did this help?"


def test_feedback_options(monkeypatch):
    monkeypatch.delenv("FEEDBACK_OPTIONS", raising=False)
    assert config.get_feedback_options() == ["Works perfectly", "Needs tweaks"]

    monkeypatch.setenv("FEEDBACK_OPTIONS", " Great ,  Okay , Ignore ")
    config.clear_config_cache()
    assert config.get_feedback_options() == ["Great", "Okay"]

    monkeypatch.setenv("FEEDBACK_OPTIONS", " , ")
    config.clear_config_cache()
    assert config.get_feedback_options() == ["Works perfectly", "Needs tweaks"]
