from __future__ import annotations

import logging


def configure_app_logging() -> None:
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    logging.getLogger("retirement_financial_tracking").setLevel(logging.INFO)
