from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    phone_number = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_email_verified = db.Column(db.Boolean, default=False)
    last_login_at = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, 
                         onupdate=datetime.utcnow)
    
    # Relationships
    managed_lots = db.relationship('ParkingLot', backref='manager', lazy=True,
                                  foreign_keys='ParkingLot.manager_id')
    
    # Backrefs (defined in other models):
    # - bookings (from Booking model)
    # - complaints (from Complaint model)
    
    @property
    def full_name(self):
        """Return the full name of the user."""
        return f"{self.first_name} {self.last_name}"
    
    def set_password(self, password):
        """Set the user's password."""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Check if the provided password matches the user's hashed password."""
        return check_password_hash(self.password_hash, password)
    
    def get_active_bookings(self):
        """Get all active bookings for the user."""
        from . import Booking
        return Booking.query.filter_by(user_id=self.id, status=Booking.STATUS_CONFIRMED).all()
    
    def get_booking_history(self, limit=10):
        """Get the user's booking history."""
        from . import Booking
        return (Booking.query
                .filter_by(user_id=self.id)
                .order_by(Booking.created_at.desc())
                .limit(limit)
                .all())
    
    def __repr__(self):
        return f'<User {self.email}>'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))