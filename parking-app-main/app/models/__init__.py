# Import all models for easier access
from .user import User
from .parking import (
    Address,
    ParkingLot,
    ParkingSpot,
    Booking,
    Transaction,
    Complaint,
    Payment
)

# Make models available when importing from app.models
__all__ = [
    'User',
    'Address',
    'ParkingLot',
    'ParkingSpot',
    'Booking',
    'Transaction',
    'Complaint',
    'Payment'
]