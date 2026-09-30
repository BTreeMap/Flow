"""The consistency guarantee, asserted rather than assumed.

These tests exist because the rule they check used to be a convention spread
across 56 independent raise sites, and conventions drift. Each test here fails
if a future variant is added without honouring the rule.
"""

from __future__ import annotations

import pytest
from app.errors import AppError, Fault, http_status


class TestTheRuleHoldsForEveryVariant:
    """The rule is a property of the whole domain, not of individual sites."""

    @pytest.mark.parametrize("fault", list(Fault))
    def test_status_is_defined_and_in_range(self, fault: Fault) -> None:
        """Total: every variant maps, and to a real client-error/server-error code."""
        assert 400 <= http_status(fault) < 600

    @pytest.mark.parametrize("fault", list(Fault))
    def test_caller_visible_faults_are_4xx_and_ours_are_5xx(self, fault: Fault) -> None:
        """The rule itself.

        A caller-visible fault must be a 4xx — anything else is replaced by the
        CDN and loses its detail. A fault of ours must be a 5xx, because no
        caller action changes the outcome.
        """
        status = http_status(fault)
        if fault.is_caller_visible:
            assert 400 <= status < 500, f"{fault.name} is caller-visible but not 4xx"
        else:
            assert 500 <= status < 600, f"{fault.name} is ours but not 5xx"

    def test_exactly_one_variant_is_ours(self) -> None:
        """A second internal variant would need its own justification here."""
        ours = [fault for fault in Fault if not fault.is_caller_visible]
        assert ours == [Fault.INTERNAL]

    def test_upstream_failure_is_caller_visible(self) -> None:
        """The incident this module exists for.

        A provider outage reported as 5xx is replaced by the CDN's error page,
        so the reason never reaches the client.
        """
        assert Fault.UPSTREAM_UNAVAILABLE.is_caller_visible
        assert http_status(Fault.UPSTREAM_UNAVAILABLE) == 424


class TestAppError:
    def test_status_is_derived_not_supplied(self) -> None:
        """No constructor accepts a status, so no site can pick an inconsistent one."""
        assert AppError(Fault.NOT_FOUND, "Session not found").status_code == 404
        assert AppError(Fault.INTERNAL, "Failed to load sessions").status_code == 500

    def test_detail_survives_as_the_exception_message(self) -> None:
        error = AppError(Fault.CONFLICT, "Turn conflict")
        assert error.detail == "Turn conflict"
        # HTTPException.__str__ prefixes the status; that is the framework's
        # format, inherited rather than overridden.
        assert str(error) == "409: Turn conflict"

    def test_repr_names_the_fault(self) -> None:
        assert repr(AppError(Fault.MALFORMED, "bad code")) == (
            "AppError(MALFORMED, 'bad code')"
        )


def test_app_error_is_an_http_exception() -> None:
    """Existing `except HTTPException` guards must keep catching these."""
    from fastapi import HTTPException

    error = AppError(Fault.NOT_FOUND, "Session not found")
    assert isinstance(error, HTTPException)
    assert error.status_code == 404
    assert error.detail == "Session not found"
