import uvicorn

from app.config import get_host, get_port
from app.logging_conf import build_logging_config


def main() -> None:
    """Run the API server.

    Logging is described in one place (:func:`app.logging_conf.build_logging_config`)
    and handed to uvicorn via ``log_config`` so the server, its access log, and
    the application all share a single configuration instead of two competing
    logging setups. The application lifespan re-applies the same description, so
    ``uvicorn app.main:app`` (without this launcher) is configured identically.
    """
    uvicorn.run(
        "app.main:app",
        host=get_host(),
        port=get_port(),
        log_config=build_logging_config(),
    )


if __name__ == "__main__":
    main()
