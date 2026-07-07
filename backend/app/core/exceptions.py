from __future__ import annotations

from fastapi import HTTPException, status


class SanketBaseError(HTTPException):
    """Base for all SANKET domain exceptions."""


class AuthenticationError(SanketBaseError):
    def __init__(self, detail: str = "Authentication required") -> None:
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class InvalidCredentialsError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__("Invalid email or password")


class TokenExpiredError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__("Token has expired")


class TokenInvalidError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__("Token is invalid or malformed")


class RefreshTokenInvalidError(AuthenticationError):
    def __init__(self) -> None:
        super().__init__("Refresh token is invalid or has been revoked")


class PermissionDeniedError(SanketBaseError):
    def __init__(self, detail: str = "Insufficient permissions") -> None:
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class NotFoundError(SanketBaseError):
    def __init__(self, resource: str = "Resource") -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{resource} not found",
        )


class ConflictError(SanketBaseError):
    def __init__(self, detail: str = "Resource already exists") -> None:
        super().__init__(status_code=status.HTTP_409_CONFLICT, detail=detail)


class ValidationError(SanketBaseError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )


class TenantSuspendedError(SanketBaseError):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Tenant account is suspended. Contact support.",
        )


class IndustryNotEnabledError(SanketBaseError):
    def __init__(self, industry: str) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Industry '{industry}' is not enabled for this tenant",
        )


class SKULimitExceededError(SanketBaseError):
    def __init__(self, limit: int) -> None:
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"SKU limit of {limit} reached. Upgrade your plan.",
        )


class GxPComplianceError(SanketBaseError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"GxP compliance violation: {detail}",
        )


class DatabaseError(SanketBaseError):
    def __init__(self, detail: str = "A database error occurred") -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )
