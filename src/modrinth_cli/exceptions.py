class ModrinthException(Exception):
    """Base class for all modrinth-cli exceptions"""
    pass


class DependencyError(ModrinthException):
    """Raised when a dependency error is found."""
    pass


class DependencyConflictError(DependencyError):
    """Raised when a dependency conflict is found."""
    pass

class DependencyNotFoundError(DependencyError):
    """Raised when a dependency is missing."""
    pass
