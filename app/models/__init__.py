# Import every model here so Alembic autogenerate sees it via Base.metadata.
from app.models.booking import Booking  # noqa: F401
from app.models.event import Event  # noqa: F401
from app.models.seat import Seat  # noqa: F401
from app.models.user import User  # noqa: F401
