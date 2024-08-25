#!/usr/bin/env python3
"""
YACE returns errors except for the truly exceptional cases.
"""
from pydantic import BaseModel


class Error(BaseModel):
    message: str

    def __str__(self):
        return f"error.message: {self.message}"


class ParseError(Error):
    filename: str
    line: int
    column: int

    @classmethod
    def from_exception(cls, exception, cursor):
        errors = "\n".join(
            [f"{count}: {error}" for count, error in enumerate(exception.errors())]
        )

        return cls(
            message=errors,
            filename=cursor.location.file.name if cursor.location.file else "unknown",
            line=cursor.location.line if cursor.location.line else -1,
            column=cursor.location.column if cursor.location.column else -1,
        )

    @classmethod
    def from_cursor(cls, message, cursor):
        return cls(
            message=message,
            filename=cursor.location.file.name if cursor.location.file else "unknown",
            line=cursor.location.line if cursor.location.line else -1,
            column=cursor.location.column if cursor.location.column else -1,
        )

    def __str__(self):
        return (
            f"{self.filename}; line: {self.line}, "
            f"column: {self.column}, error: {self.message}"
        )


class UnsupportedDatatype(ParseError):
    @classmethod
    def from_cursor(cls, cursor, message=None):
        if not message:
            message = f"Unsupported datatype({cursor.type.spelling})"

        return cls(
            message=message,
            filename=cursor.location.file.name if cursor.location.file else "unknown",
            line=cursor.location.line if cursor.location.line else -1,
            column=cursor.location.column if cursor.location.column else -1,
        )


class TransformationError(Exception):
    """Something went wrong during a yid-transformation"""

    pass


class ToolError(Exception):
    """Exception raised when a tool exists with non-zero returncode"""

    pass


class InvalidModelData(Exception):
    """The data given to entity instantion is not valid"""

    pass
