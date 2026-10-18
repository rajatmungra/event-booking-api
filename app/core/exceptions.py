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


class SeatsAlreadyExist(AppError):
    status_code = 409
    code = "SEATS_ALREADY_EXIST"
    message = "This event already has a seat layout."


class SeatNotFound(AppError):
    status_code = 404
    code = "SEAT_NOT_FOUND"
    message = "One or more seats don't exist for this event."


class SeatUnavailable(AppError):
    status_code = 409
    code = "SEAT_UNAVAILABLE"
    message = "One or more seats are already held or booked."


class BookingNotFound(AppError):
    status_code = 404
    code = "BOOKING_NOT_FOUND"
    message = "Booking not found."


class InvalidBookingStatus(AppError):
    status_code = 409
    code = "INVALID_BOOKING_STATUS"
    message = "This action isn't allowed in the booking's current status."


class BookingExpired(AppError):
    status_code = 410
    code = "BOOKING_EXPIRED"
    message = "The seat hold for this booking has expired."


class IdempotencyKeyReused(AppError):
    status_code = 409
    code = "IDEMPOTENCY_KEY_REUSED"
    message = "This Idempotency-Key was already used for a different booking."
