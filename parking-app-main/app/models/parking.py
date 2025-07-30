from datetime import datetime
from app import db
from sqlalchemy import CheckConstraint

class Address(db.Model):
    """Address model for storing location information."""
    __tablename__ = 'addresses'
    
    id = db.Column(db.Integer, primary_key=True)
    street = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100))
    postal_code = db.Column(db.String(20), nullable=False)
    country = db.Column(db.String(100), nullable=False, default='United States')
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    parking_lots = db.relationship('ParkingLot', back_populates='address', lazy=True)
    
    def __repr__(self):
        return f'<Address {self.street}, {self.city}, {self.state} {self.postal_code}>'


class ParkingLot(db.Model):
    """Parking lot model for managing parking facilities."""
    __tablename__ = 'parking_lots'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    total_spots = db.Column(db.Integer, nullable=False, default=0)
    available_spots = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, default=True)
    hourly_rate = db.Column(db.Numeric(10, 2), nullable=False)
    daily_rate = db.Column(db.Numeric(10, 2))
    monthly_rate = db.Column(db.Numeric(10, 2))
    opening_time = db.Column(db.Time, nullable=False)
    closing_time = db.Column(db.Time, nullable=False)
    address_id = db.Column(db.Integer, db.ForeignKey('addresses.id'), nullable=False)
    manager_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    address = db.relationship('Address', back_populates='parking_lots')
    spots = db.relationship('ParkingSpot', back_populates='parking_lot', lazy=True,
                           cascade='all, delete-orphan')
    
    # Backrefs:
    # - manager (from User.managed_lots)
    
    def update_spot_counts(self):
        """Update the total and available spot counts based on related spots."""
        from sqlalchemy import func
        
        # Get counts from the database
        counts = db.session.query(
            func.count(ParkingSpot.id),
            func.sum(db.case([(ParkingSpot.is_available == True, 1)], else_=0))
        ).filter(ParkingSpot.parking_lot_id == self.id).first()
        
        total, available = counts or (0, 0)
        self.total_spots = total
        self.available_spots = available or 0
        return self
    
    def get_available_spots(self):
        """Get all available parking spots in this lot."""
        return [spot for spot in self.spots if spot.is_available]
    
    def get_handicap_spots(self):
        """Get all handicap-accessible spots in this lot."""
        return [spot for spot in self.spots if spot.is_handicap]
    
    def get_covered_spots(self):
        """Get all covered parking spots in this lot."""
        return [spot for spot in self.spots if spot.is_covered]
    
    def get_spot_by_number(self, spot_number):
        """Get a spot by its spot number."""
        return next((spot for spot in self.spots if spot.spot_number == spot_number), None)
    
    def is_open(self, current_time=None):
        """Check if the parking lot is currently open."""
        if current_time is None:
            current_time = datetime.now().time()
        return self.opening_time <= current_time <= self.closing_time
    
    def __repr__(self):
        return f'<ParkingLot {self.name} (ID: {self.id})>'


class ParkingSpot(db.Model):
    """Parking spot model for individual parking spaces."""
    __tablename__ = 'parking_spots'
    
    # Spot types
    TYPE_REGULAR = 'regular'
    TYPE_HANDICAP = 'handicap'
    TYPE_ELECTRIC = 'electric'
    TYPE_MOTORCYCLE = 'motorcycle'
    
    id = db.Column(db.Integer, primary_key=True)
    spot_number = db.Column(db.String(20), nullable=False)
    floor = db.Column(db.Integer, default=1, nullable=False)
    spot_type = db.Column(db.String(20), default=TYPE_REGULAR, nullable=False)
    is_handicap = db.Column(db.Boolean, default=False, nullable=False)
    is_covered = db.Column(db.Boolean, default=False, nullable=False)
    is_available = db.Column(db.Boolean, default=True, nullable=False)
    has_charger = db.Column(db.Boolean, default=False, nullable=False)
    notes = db.Column(db.Text)
    parking_lot_id = db.Column(db.Integer, db.ForeignKey('parking_lots.id', ondelete='CASCADE'), 
                             nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    parking_lot = db.relationship('ParkingLot', back_populates='spots')
    bookings = db.relationship('Booking', back_populates='spot', lazy=True,
                             cascade='all, delete-orphan')
    
    __table_args__ = (
        db.UniqueConstraint('parking_lot_id', 'spot_number', name='uq_spot_number_per_lot'),
    )
    
    @property
    def display_name(self):
        """Get a display-friendly name for the spot."""
        return f"{self.parking_lot.name} - {self.spot_number}" if self.parking_lot else self.spot_number
    
    def is_available_for_booking(self, start_time, end_time):
        """Check if the spot is available for booking during the specified time range."""
        from sqlalchemy import and_, or_
        
        # Check if spot is marked as available
        if not self.is_available:
            return False
            
        # Check for overlapping bookings
        overlapping_booking = db.session.query(Booking).filter(
            Booking.spot_id == self.id,
            Booking.status.in_([Booking.STATUS_CONFIRMED, Booking.STATUS_PENDING]),
            or_(
                and_(Booking.start_time <= start_time, Booking.end_time > start_time),
                and_(Booking.start_time < end_time, Booking.end_time >= end_time),
                and_(Booking.start_time >= start_time, Booking.end_time <= end_time)
            )
        ).first()
        
        return overlapping_booking is None
    
    def get_current_booking(self):
        """Get the current active booking for this spot, if any."""
        now = datetime.utcnow()
        return db.session.query(Booking).filter(
            Booking.spot_id == self.id,
            Booking.status == Booking.STATUS_CONFIRMED,
            Booking.start_time <= now,
            Booking.end_time >= now
        ).first()
    
    def get_upcoming_bookings(self, limit=5):
        """Get upcoming bookings for this spot."""
        now = datetime.utcnow()
        return (db.session.query(Booking)
                .filter(
                    Booking.spot_id == self.id,
                    Booking.status == Booking.STATUS_CONFIRMED,
                    Booking.start_time >= now
                )
                .order_by(Booking.start_time.asc())
                .limit(limit)
                .all())
    
    def to_dict(self):
        """Convert the spot to a dictionary representation."""
        return {
            'id': self.id,
            'spot_number': self.spot_number,
            'floor': self.floor,
            'spot_type': self.spot_type,
            'is_handicap': self.is_handicap,
            'is_covered': self.is_covered,
            'has_charger': self.has_charger,
            'is_available': self.is_available,
            'parking_lot_id': self.parking_lot_id,
            'display_name': self.display_name
        }
    
    def __repr__(self):
        return f'<ParkingSpot {self.spot_number} (Lot {self.parking_lot_id})>'


class Booking(db.Model):
    """Booking model for parking spot reservations."""
    __tablename__ = 'bookings'
    
    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_CONFIRMED = 'confirmed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_COMPLETED = 'completed'
    STATUS_CHECKED_IN = 'checked_in'
    STATUS_NO_SHOW = 'no_show'
    
    # Cancellation reasons
    CANCELLATION_BY_USER = 'user_cancellation'
    CANCELLATION_BY_SYSTEM = 'system_cancellation'
    CANCELLATION_OTHER = 'other'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    spot_id = db.Column(db.Integer, db.ForeignKey('parking_spots.id', ondelete='CASCADE'), 
                       nullable=False)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    end_time = db.Column(db.DateTime, nullable=False, index=True)
    status = db.Column(db.String(20), default=STATUS_PENDING, nullable=False, index=True)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    vehicle_plate = db.Column(db.String(20))
    notes = db.Column(db.Text)
    cancellation_reason = db.Column(db.String(50))
    cancellation_notes = db.Column(db.Text)
    checked_in_at = db.Column(db.DateTime)
    checked_out_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('bookings', lazy=True))
    spot = db.relationship('ParkingSpot', back_populates='bookings')
    transaction = db.relationship('Transaction', back_populates='booking', uselist=False, 
                                 cascade='all, delete-orphan')
    
    __table_args__ = (
        CheckConstraint('end_time > start_time', name='check_booking_dates'),
        {}
    )
    
    @property
    def duration_hours(self):
        """Calculate the duration of the booking in hours."""
        if not self.start_time or not self.end_time:
            return 0
        duration = self.end_time - self.start_time
        return round(duration.total_seconds() / 3600, 2)
    
    @property
    def is_active(self):
        """Check if the booking is currently active."""
        now = datetime.utcnow()
        return (self.status == self.STATUS_CONFIRMED and 
                self.start_time <= now <= self.end_time)
    
    @property
    def is_upcoming(self):
        """Check if the booking is in the future."""
        return (self.status == self.STATUS_CONFIRMED and 
                self.start_time > datetime.utcnow())
    
    @property
    def is_past(self):
        """Check if the booking is in the past."""
        return self.end_time < datetime.utcnow()
    
    def cancel(self, reason=CANCELLATION_OTHER, notes=None):
        """Cancel this booking."""
        if self.status in [self.STATUS_CANCELLED, self.STATUS_COMPLETED]:
            return False
            
        self.status = self.STATUS_CANCELLED
        self.cancellation_reason = reason
        self.cancellation_notes = notes
        
        # If there's a transaction, mark it as refunded if needed
        if self.transaction and self.transaction.status == Transaction.STATUS_COMPLETED:
            self.transaction.status = Transaction.STATUS_REFUNDED
            
        return True
    
    def check_in(self):
        """Mark the booking as checked in."""
        if self.status != self.STATUS_CONFIRMED:
            return False
            
        self.status = self.STATUS_CHECKED_IN
        self.checked_in_at = datetime.utcnow()
        return True
    
    def check_out(self):
        """Mark the booking as completed with check out."""
        if self.status not in [self.STATUS_CONFIRMED, self.STATUS_CHECKED_IN]:
            return False
            
        self.status = self.STATUS_COMPLETED
        self.checked_out_at = datetime.utcnow()
        return True
    
    def calculate_amount(self, current_time=None):
        """Calculate the amount for the booking based on rates and duration."""
        if not self.spot or not self.spot.parking_lot:
            return 0
            
        if current_time is None:
            current_time = datetime.utcnow()
            
        # If booking is in the future, use the full duration
        if current_time < self.start_time:
            duration_hours = self.duration_hours
        # If booking is in progress, calculate remaining time
        elif current_time < self.end_time:
            duration = self.end_time - current_time
            duration_hours = duration.total_seconds() / 3600
        # If booking is completed, return the total amount
        else:
            return self.total_amount
            
        # Get rates from the parking lot
        lot = self.spot.parking_lot
        
        # Calculate amount based on hourly rate
        amount = round(float(lot.hourly_rate) * duration_hours, 2)
        
        # If daily rate is cheaper, use that
        if lot.daily_rate and (duration_hours >= 24 or 
                              (lot.daily_rate / 24) < lot.hourly_rate):
            days = max(1, int(duration_hours / 24) + (1 if duration_hours % 24 > 0 else 0))
            amount = min(amount, float(lot.daily_rate) * days)
            
        return amount
    
    def to_dict(self, include_related=False):
        """Convert the booking to a dictionary representation."""
        result = {
            'id': self.id,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'status': self.status,
            'total_amount': float(self.total_amount) if self.total_amount is not None else 0.0,
            'duration_hours': self.duration_hours,
            'is_active': self.is_active,
            'is_upcoming': self.is_upcoming,
            'is_past': self.is_past,
            'vehicle_plate': self.vehicle_plate,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'checked_in_at': self.checked_in_at.isoformat() if self.checked_in_at else None,
            'checked_out_at': self.checked_out_at.isoformat() if self.checked_out_at else None,
        }
        
        if include_related and self.spot:
            result['spot'] = self.spot.to_dict()
            if self.spot.parking_lot:
                result['parking_lot'] = {
                    'id': self.spot.parking_lot.id,
                    'name': self.spot.parking_lot.name,
                    'address': str(self.spot.parking_lot.address) if self.spot.parking_lot.address else None
                }
                
        return result
    
    @classmethod
    def get_user_bookings(cls, user_id, status=None, upcoming_only=False, past_only=False, 
                         limit=None, offset=0):
        """Get bookings for a user with optional filters."""
        query = cls.query.filter_by(user_id=user_id)
        
        if status:
            if isinstance(status, (list, tuple)):
                query = query.filter(cls.status.in_(status))
            else:
                query = query.filter_by(status=status)
                
        now = datetime.utcnow()
        if upcoming_only:
            query = query.filter(cls.end_time >= now)
        elif past_only:
            query = query.filter(cls.end_time < now)
            
        query = query.order_by(cls.start_time.asc())
        
        if limit is not None:
            query = query.limit(limit).offset(offset)
            
        return query.all()
    
    def __repr__(self):
        return f'<Booking {self.id} - {self.status}>'


class Transaction(db.Model):
    """Transaction model for payment records."""
    __tablename__ = 'transactions'
    
    # Status constants
    STATUS_PENDING = 'pending'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_REFUNDED = 'refunded'
    STATUS_PARTIALLY_REFUNDED = 'partially_refunded'
    STATUS_DECLINED = 'declined'
    
    # Payment methods
    METHOD_CREDIT_CARD = 'credit_card'
    METHOD_DEBIT_CARD = 'debit_card'
    METHOD_NET_BANKING = 'net_banking'
    METHOD_UPI = 'upi'
    METHOD_WALLET = 'wallet'
    METHOD_CASH = 'cash'
    
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id', ondelete='CASCADE'), 
                          nullable=False, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(50), nullable=False, index=True)
    transaction_id = db.Column(db.String(100), unique=True, index=True)
    status = db.Column(db.String(30), default=STATUS_PENDING, nullable=False, index=True)
    currency = db.Column(db.String(3), default='USD', nullable=False)
    payment_gateway = db.Column(db.String(50))
    gateway_transaction_id = db.Column(db.String(100), index=True)
    gateway_response = db.Column(db.JSON)  # Raw response from payment gateway
    refund_amount = db.Column(db.Numeric(10, 2), default=0.0)
    refund_reason = db.Column(db.Text)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    booking = db.relationship('Booking', back_populates='transaction')
    
    @property
    def is_successful(self):
        """Check if the transaction was successful."""
        return self.status in [self.STATUS_COMPLETED, self.STATUS_REFUNDED, 
                             self.STATUS_PARTIALLY_REFUNDED]
    
    @property
    def is_refunded(self):
        """Check if the transaction has been refunded."""
        return self.status in [self.STATUS_REFUNDED, self.STATUS_PARTIALLY_REFUNDED]
    
    def mark_as_completed(self, gateway_transaction_id=None, gateway_response=None):
        """Mark the transaction as completed."""
        if self.status != self.STATUS_PENDING:
            return False
            
        self.status = self.STATUS_COMPLETED
        self.gateway_transaction_id = gateway_transaction_id
        self.gateway_response = gateway_response
        self.payment_date = datetime.utcnow()
        return True
    
    def mark_as_failed(self, reason=None, gateway_response=None):
        """Mark the transaction as failed."""
        if self.status != self.STATUS_PENDING:
            return False
            
        self.status = self.STATUS_FAILED
        self.gateway_response = gateway_response
        self.refund_reason = reason
        return True
    
    def process_refund(self, amount=None, reason=None, gateway_response=None):
        """Process a refund for this transaction."""
        if self.status != self.STATUS_COMPLETED:
            return False
            
        if amount is None:
            amount = self.amount
            
        amount = min(float(amount), float(self.amount))
        
        if amount == float(self.amount):
            self.status = self.STATUS_REFUNDED
        else:
            self.status = self.STATUS_PARTIALLY_REFUNDED
            
        self.refund_amount = amount
        self.refund_reason = reason
        self.gateway_response = gateway_response
        self.updated_at = datetime.utcnow()
        return True
    
    def to_dict(self, include_booking=False):
        """Convert the transaction to a dictionary representation."""
        result = {
            'id': self.id,
            'amount': float(self.amount) if self.amount is not None else 0.0,
            'currency': self.currency,
            'payment_method': self.payment_method,
            'status': self.status,
            'transaction_id': self.transaction_id,
            'payment_date': self.payment_date.isoformat() if self.payment_date else None,
            'refund_amount': float(self.refund_amount) if self.refund_amount is not None else 0.0,
            'is_successful': self.is_successful,
            'is_refunded': self.is_refunded,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_booking and self.booking:
            result['booking'] = {
                'id': self.booking.id,
                'start_time': self.booking.start_time.isoformat() if self.booking.start_time else None,
                'end_time': self.booking.end_time.isoformat() if self.booking.end_time else None,
                'status': self.booking.status
            }
            
        return result
    
    @classmethod
    def get_user_transactions(cls, user_id, status=None, payment_method=None, 
                            start_date=None, end_date=None, limit=None, offset=0):
        """Get transactions for a user with optional filters."""
        from sqlalchemy import and_
        
        query = cls.query.join(Booking).filter(Booking.user_id == user_id)
        
        if status:
            if isinstance(status, (list, tuple)):
                query = query.filter(cls.status.in_(status))
            else:
                query = query.filter_by(status=status)
                
        if payment_method:
            query = query.filter_by(payment_method=payment_method)
            
        if start_date:
            query = query.filter(cls.payment_date >= start_date)
            
        if end_date:
            query = query.filter(cls.payment_date <= end_date)
            
        query = query.order_by(cls.payment_date.desc())
        
        if limit is not None:
            query = query.limit(limit).offset(offset)
            
        return query.all()
    
    def __repr__(self):
        return f'<Transaction {self.id} - {self.status} - ${self.amount}>'


class Complaint(db.Model):
    """Complaint model for user complaints and feedback."""
    __tablename__ = 'complaints'
    
    # Status constants
    STATUS_OPEN = 'open'
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_RESOLVED = 'resolved'
    STATUS_CLOSED = 'closed'
    STATUS_REJECTED = 'rejected'
    
    # Priority levels
    PRIORITY_LOW = 'low'
    PRIORITY_MEDIUM = 'medium'
    PRIORITY_HIGH = 'high'
    PRIORITY_CRITICAL = 'critical'
    
    # Complaint types
    TYPE_GENERAL = 'general'
    TYPE_BOOKING = 'booking'
    TYPE_PAYMENT = 'payment'
    TYPE_TECHNICAL = 'technical'
    TYPE_FEEDBACK = 'feedback'
    TYPE_OTHER = 'other'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), 
                       nullable=False, index=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id', ondelete='SET NULL'),
                          index=True)
    complaint_type = db.Column(db.String(30), default=TYPE_GENERAL, nullable=False, index=True)
    subject = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default=STATUS_OPEN, nullable=False, index=True)
    priority = db.Column(db.String(20), default=PRIORITY_MEDIUM, nullable=False, index=True)
    resolution = db.Column(db.Text)
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', foreign_keys=[user_id], 
                          backref=db.backref('filed_complaints', lazy=True))
    booking = db.relationship('Booking', backref=db.backref('related_complaints', lazy=True))
    resolver = db.relationship('User', foreign_keys=[resolved_by], 
                              backref=db.backref('resolved_complaints', lazy=True))
    assignee = db.relationship('User', foreign_keys=[assigned_to], 
                              backref=db.backref('assigned_complaints', lazy=True))
    
    @property
    def is_open(self):
        """Check if the complaint is still open."""
        return self.status in [self.STATUS_OPEN, self.STATUS_IN_PROGRESS]
    
    @property
    def is_resolved(self):
        """Check if the complaint has been resolved."""
        return self.status == self.STATUS_RESOLVED
    
    @property
    def is_closed(self):
        """Check if the complaint is closed (resolved or rejected)."""
        return self.status in [self.STATUS_CLOSED, self.STATUS_RESOLVED, self.STATUS_REJECTED]
    
    def assign(self, user_id):
        """Assign the complaint to a staff member."""
        if self.status == self.STATUS_OPEN:
            self.status = self.STATUS_IN_PROGRESS
        self.assigned_to = user_id
        self.updated_at = datetime.utcnow()
    
    def resolve(self, resolution, resolved_by_user_id):
        """Mark the complaint as resolved."""
        self.status = self.STATUS_RESOLVED
        self.resolution = resolution
        self.resolved_by = resolved_by_user_id
        self.resolved_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def close(self, resolution=None, resolved_by_user_id=None):
        """Close the complaint, optionally with a resolution."""
        self.status = self.STATUS_CLOSED
        if resolution:
            self.resolution = resolution
        if resolved_by_user_id:
            self.resolved_by = resolved_by_user_id
            self.resolved_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
    
    def reject(self, reason):
        """Reject the complaint with a reason."""
        self.status = self.STATUS_REJECTED
        self.resolution = reason
        self.updated_at = datetime.utcnow()
    
    def to_dict(self, include_related=False):
        """Convert the complaint to a dictionary representation."""
        result = {
            'id': self.id,
            'type': self.complaint_type,
            'subject': self.subject,
            'status': self.status,
            'priority': self.priority,
            'is_open': self.is_open,
            'is_resolved': self.is_resolved,
            'is_closed': self.is_closed,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_related:
            result['user'] = {
                'id': self.user.id,
                'name': self.user.full_name,
                'email': self.user.email
            }
            
            if self.booking:
                result['booking'] = {
                    'id': self.booking.id,
                    'start_time': self.booking.start_time.isoformat() if self.booking.start_time else None,
                    'end_time': self.booking.end_time.isoformat() if self.booking.end_time else None
                }
                
            if self.assignee:
                result['assigned_to'] = {
                    'id': self.assignee.id,
                    'name': self.assignee.full_name
                }
                
            if self.resolved_at:
                result['resolved_at'] = self.resolved_at.isoformat()
                
            if self.resolver:
                result['resolved_by'] = {
                    'id': self.resolver.id,
                    'name': self.resolver.full_name
                }
                
        return result
    
    @classmethod
    def get_user_complaints(cls, user_id, status=None, complaint_type=None, 
                           priority=None, limit=None, offset=0):
        """Get complaints for a user with optional filters."""
        query = cls.query.filter_by(user_id=user_id)
        
        if status:
            if isinstance(status, (list, tuple)):
                query = query.filter(cls.status.in_(status))
            else:
                query = query.filter_by(status=status)
                
        if complaint_type:
            query = query.filter_by(complaint_type=complaint_type)
            
        if priority:
            if isinstance(priority, (list, tuple)):
                query = query.filter(cls.priority.in_(priority))
            else:
                query = query.filter_by(priority=priority)
                
        query = query.order_by(cls.created_at.desc())
        
        if limit is not None:
            query = query.limit(limit).offset(offset)
            
        return query.all()
    
    @classmethod
    def get_open_complaints(cls, priority=None, assigned_to=None):
        """Get all open complaints, optionally filtered by priority and assignee."""
        query = cls.query.filter(
            cls.status.in_([cls.STATUS_OPEN, cls.STATUS_IN_PROGRESS])
        )
        
        if priority:
            if isinstance(priority, (list, tuple)):
                query = query.filter(cls.priority.in_(priority))
            else:
                query = query.filter_by(priority=priority)
                
        if assigned_to:
            query = query.filter_by(assigned_to=assigned_to)
            
        return query.order_by(
            db.case(
                [(cls.priority == cls.PRIORITY_CRITICAL, 1),
                 (cls.priority == cls.PRIORITY_HIGH, 2),
                 (cls.priority == cls.PRIORITY_MEDIUM, 3),
                 (cls.priority == cls.PRIORITY_LOW, 4)],
                else_=5
            ),
            cls.created_at.asc()
        ).all()
    
    def __repr__(self):
        return f'<Complaint {self.id} - {self.status} - {self.priority} priority>'


class Payment(db.Model):
    """Payment model for tracking all payment transactions."""
    __tablename__ = 'payments'
    
    # Payment statuses
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'
    STATUS_COMPLETED = 'completed'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_REFUNDED = 'refunded'
    STATUS_PARTIALLY_REFUNDED = 'partially_refunded'
    
    # Payment methods
    METHOD_CREDIT_CARD = 'credit_card'
    METHOD_DEBIT_CARD = 'debit_card'
    METHOD_PAYPAL = 'paypal'
    METHOD_APPLE_PAY = 'apple_pay'
    METHOD_GOOGLE_PAY = 'google_pay'
    METHOD_BANK_TRANSFER = 'bank_transfer'
    METHOD_WALLET = 'wallet'
    METHOD_CASH = 'cash'
    
    # Payment types
    TYPE_BOOKING = 'booking'
    TYPE_DEPOSIT = 'deposit'
    TYPE_REFUND = 'refund'
    TYPE_PENALTY = 'penalty'
    TYPE_SUBSCRIPTION = 'subscription'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Core payment information
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING)
    payment_method = db.Column(db.String(20), nullable=False)
    payment_type = db.Column(db.String(20), nullable=False, default=TYPE_BOOKING)
    
    # External payment gateway information
    stripe_payment_intent_id = db.Column(db.String(255), unique=True)
    stripe_charge_id = db.Column(db.String(255))
    paypal_transaction_id = db.Column(db.String(255))
    gateway_response = db.Column(db.Text)  # Store full gateway response as JSON
    
    # Transaction details
    description = db.Column(db.String(255))
    reference_number = db.Column(db.String(50), unique=True)  # Internal reference
    
    # Refund information
    refund_amount = db.Column(db.Numeric(10, 2), default=0)
    refund_reason = db.Column(db.String(255))
    refunded_at = db.Column(db.DateTime)
    
    # Failure information
    failure_code = db.Column(db.String(50))
    failure_message = db.Column(db.String(255))
    
    # Relationships
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    processed_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # Admin who processed refund
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    processed_at = db.Column(db.DateTime)  # When payment was completed
    
    # Relationships
    booking = db.relationship('Booking', backref='payments')
    user = db.relationship('User', foreign_keys=[user_id], backref='payments')
    processor = db.relationship('User', foreign_keys=[processed_by])
    
    # Constraints
    __table_args__ = (
        CheckConstraint('amount > 0', name='positive_amount'),
        CheckConstraint('refund_amount >= 0', name='non_negative_refund'),
        CheckConstraint('refund_amount <= amount', name='refund_not_exceeding_amount'),
    )
    
    def __init__(self, **kwargs):
        super(Payment, self).__init__(**kwargs)
        if not self.reference_number:
            self.reference_number = self.generate_reference_number()
    
    @staticmethod
    def generate_reference_number():
        """Generate a unique reference number for the payment."""
        import uuid
        import time
        timestamp = str(int(time.time()))
        unique_id = str(uuid.uuid4())[:8].upper()
        return f"PAY-{timestamp}-{unique_id}"
    
    @property
    def is_pending(self):
        """Check if payment is pending."""
        return self.status == self.STATUS_PENDING
    
    @property
    def is_processing(self):
        """Check if payment is being processed."""
        return self.status == self.STATUS_PROCESSING
    
    @property
    def is_completed(self):
        """Check if payment is completed successfully."""
        return self.status == self.STATUS_COMPLETED
    
    @property
    def is_failed(self):
        """Check if payment failed."""
        return self.status == self.STATUS_FAILED
    
    @property
    def is_cancelled(self):
        """Check if payment was cancelled."""
        return self.status == self.STATUS_CANCELLED
    
    @property
    def is_refunded(self):
        """Check if payment was fully refunded."""
        return self.status == self.STATUS_REFUNDED
    
    @property
    def is_partially_refunded(self):
        """Check if payment was partially refunded."""
        return self.status == self.STATUS_PARTIALLY_REFUNDED
    
    @property
    def net_amount(self):
        """Get the net amount after refunds."""
        return float(self.amount) - float(self.refund_amount or 0)
    
    @property
    def can_be_refunded(self):
        """Check if payment can be refunded."""
        return (self.is_completed and 
                float(self.refund_amount or 0) < float(self.amount))
    
    def mark_as_processing(self):
        """Mark payment as processing."""
        self.status = self.STATUS_PROCESSING
        self.updated_at = datetime.utcnow()
    
    def mark_as_completed(self, gateway_response=None):
        """Mark payment as completed."""
        self.status = self.STATUS_COMPLETED
        self.processed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        if gateway_response:
            self.gateway_response = gateway_response
    
    def mark_as_failed(self, failure_code=None, failure_message=None):
        """Mark payment as failed."""
        self.status = self.STATUS_FAILED
        self.failure_code = failure_code
        self.failure_message = failure_message
        self.updated_at = datetime.utcnow()
    
    def mark_as_cancelled(self, reason=None):
        """Mark payment as cancelled."""
        self.status = self.STATUS_CANCELLED
        if reason:
            self.failure_message = reason
        self.updated_at = datetime.utcnow()
    
    def process_refund(self, refund_amount, reason=None, processed_by_user=None):
        """Process a refund for this payment."""
        if not self.can_be_refunded:
            raise ValueError("Payment cannot be refunded")
        
        if refund_amount <= 0:
            raise ValueError("Refund amount must be positive")
        
        max_refund = float(self.amount) - float(self.refund_amount or 0)
        if refund_amount > max_refund:
            raise ValueError(f"Refund amount cannot exceed {max_refund}")
        
        # Update refund information
        self.refund_amount = float(self.refund_amount or 0) + refund_amount
        self.refund_reason = reason
        self.refunded_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        
        if processed_by_user:
            self.processed_by = processed_by_user.id
        
        # Update status based on refund amount
        if float(self.refund_amount) >= float(self.amount):
            self.status = self.STATUS_REFUNDED
        else:
            self.status = self.STATUS_PARTIALLY_REFUNDED
    
    def to_dict(self, include_sensitive=False):
        """Convert payment to dictionary representation."""
        result = {
            'id': self.id,
            'amount': float(self.amount),
            'currency': self.currency,
            'status': self.status,
            'payment_method': self.payment_method,
            'payment_type': self.payment_type,
            'description': self.description,
            'reference_number': self.reference_number,
            'net_amount': self.net_amount,
            'refund_amount': float(self.refund_amount or 0),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'booking_id': self.booking_id,
            'user_id': self.user_id,
        }
        
        if include_sensitive:
            result.update({
                'stripe_payment_intent_id': self.stripe_payment_intent_id,
                'stripe_charge_id': self.stripe_charge_id,
                'paypal_transaction_id': self.paypal_transaction_id,
                'failure_code': self.failure_code,
                'failure_message': self.failure_message,
                'refund_reason': self.refund_reason,
                'refunded_at': self.refunded_at.isoformat() if self.refunded_at else None,
            })
        
        return result
    
    @classmethod
    def get_user_payments(cls, user_id, status=None, payment_type=None, 
                         limit=None, offset=0):
        """Get payments for a user with optional filters."""
        query = cls.query.filter_by(user_id=user_id)
        
        if status:
            if isinstance(status, (list, tuple)):
                query = query.filter(cls.status.in_(status))
            else:
                query = query.filter_by(status=status)
        
        if payment_type:
            query = query.filter_by(payment_type=payment_type)
        
        query = query.order_by(cls.created_at.desc())
        
        if limit is not None:
            query = query.limit(limit).offset(offset)
        
        return query.all()
    
    @classmethod
    def get_booking_payments(cls, booking_id):
        """Get all payments for a specific booking."""
        return cls.query.filter_by(booking_id=booking_id).order_by(cls.created_at.desc()).all()
    
    @classmethod
    def get_revenue_stats(cls, start_date=None, end_date=None, status=None):
        """Get revenue statistics for a date range."""
        from sqlalchemy import func
        
        query = cls.query
        
        if start_date:
            query = query.filter(cls.created_at >= start_date)
        
        if end_date:
            query = query.filter(cls.created_at <= end_date)
        
        if status:
            if isinstance(status, (list, tuple)):
                query = query.filter(cls.status.in_(status))
            else:
                query = query.filter_by(status=status)
        
        stats = query.with_entities(
            func.count(cls.id).label('total_transactions'),
            func.sum(cls.amount).label('total_amount'),
            func.sum(cls.refund_amount).label('total_refunds'),
            func.avg(cls.amount).label('average_amount')
        ).first()
        
        return {
            'total_transactions': stats.total_transactions or 0,
            'total_amount': float(stats.total_amount or 0),
            'total_refunds': float(stats.total_refunds or 0),
            'net_revenue': float(stats.total_amount or 0) - float(stats.total_refunds or 0),
            'average_amount': float(stats.average_amount or 0)
        }
    
    def __repr__(self):
        return f'<Payment {self.reference_number} - {self.status} - ${self.amount}>'


# Update the Booking model to include payment-related fields
# Note: This would be added to the existing Booking class
# payment_status = db.Column(db.String(20), default='unpaid')
# total_amount = db.Column(db.Numeric(10, 2))
# paid_amount = db.Column(db.Numeric(10, 2), default=0)
# payment_due_date = db.Column(db.DateTime)