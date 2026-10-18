class AppError(Exception):
    status_code = 400
    code = "APP_ERROR"
    message = "Something went wrong."

    def __init__(self, message: str | None = None, details: dict | None = None):
        self.message = message or self.message
        self.details = details or {}
        super().__init__(self.message)


class EmailAlreadyRegistered(AppError):
    status_code = 409
    code = "EMAIL_ALREADY_REGISTERED"
    message = "A user with this email already exists."


class InvalidCredentials(AppError):
    status_code = 401
    code = "INVALID_CREDENTIALS"
    message = "Incorrect email or password."


class NotAuthenticated(AppError):
    status_code = 401
    code = "NOT_AUTHENTICATED"
    message = "Missing, invalid or expired access token."


class PermissionDenied(AppError):
    status_code = 403
    code = "PERMISSION_DENIED"
    message = "You don't have permission to do this."


class EventNotFound(AppError):
    status_code = 404
    code = "EVENT_NOT_FOUND"
    message = "Event not found."


class InvalidEventStatus(AppError):
    status_code = 409
    code = "INVALID_EVENT_STATUS"
    message = "This action isn't allowed in the event's current status."


class InvalidEventTimes(AppError):
    status_code = 422
    code = "INVALID_EVENT_TIMES"
    message = "Invalid event start or end time."
