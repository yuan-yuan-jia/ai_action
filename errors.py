import logging

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        self.message = message
        self.cause = cause
        super().__init__(message)

    def log(self) -> None:
        logger.error("%s: %s", self.__class__.__name__, self.message)
        if self.cause:
            logger.debug("Caused by", exc_info=self.cause)
