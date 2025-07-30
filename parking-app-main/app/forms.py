from flask_wtf import FlaskForm
from wtforms import StringField, DateTimeLocalField, IntegerField, SelectField, SubmitField, PasswordField, BooleanField, TextAreaField, TimeField, FloatField, DecimalField
from wtforms.validators import DataRequired, Length, Email, ValidationError, Optional, EqualTo
from datetime import datetime, timedelta
from app.models.parking import ParkingSpot
from app.models.user import User

class BookingForm(FlaskForm):
    """Form for creating a new booking."""

    parking_spot_id = SelectField('Parking Spot', coerce=int, validators=[DataRequired()])
    vehicle_plate = StringField(
        'Vehicle Plate',
        validators=[DataRequired(), Length(max=20)]
    )
    start_time = DateTimeLocalField('Start Time', validators=[DataRequired()])
    duration = SelectField('Duration (hours)', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Book Now')

    def set_spot_choices(self, spots):
        """Dynamically set select field choices based on available spots."""
        self.parking_spot_id.choices = [(s.id, f"Spot #{s.spot_number} ({s.spot_type})") for s in spots]
        
    def set_duration_choices(self):
        """Set duration choices in 30-minute increments (1-12 hours)."""
        self.duration.choices = [(i, f"{i} hour{'s' if i > 1 else ''}") for i in range(1, 25, 1)]  # 1-24 hours
    
    def validate_start_time(self, field):
        """Validate that start time is not in the past."""
        if field.data and field.data < datetime.now():
            raise ValidationError('Start time cannot be in the past. Please select a future date and time.')


class LoginForm(FlaskForm):
    """Form for user login."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Login')


class RegistrationForm(FlaskForm):
    """Form for user registration."""
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=50)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    phone_number = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    password = PasswordField('Password', validators=[
        DataRequired(), 
        Length(min=6, message='Password must be at least 6 characters long')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    submit = SubmitField('Sign Up')
    
    def validate_email(self, field):
        """Validate that email is not already registered."""
        from app.models.user import User
        if User.query.filter_by(email=field.data).first():
            raise ValidationError('Email address is already registered. Please use a different email or login instead.')


class UserForm(FlaskForm):
    """Form for creating/editing users."""
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=50)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    phone_number = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    password = PasswordField('Password', validators=[Optional(), Length(min=6)])
    is_admin = BooleanField('Admin User')
    is_active = BooleanField('Active User', default=True)
    submit = SubmitField('Save User')


class ParkingLotForm(FlaskForm):
    """Form for creating/editing parking lots."""
    name = StringField('Lot Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description', validators=[Optional(), Length(max=500)])
    
    # Address fields
    street = StringField('Street Address', validators=[DataRequired(), Length(max=200)])
    city = StringField('City', validators=[DataRequired(), Length(max=100)])
    state = StringField('State', validators=[DataRequired(), Length(max=50)])
    postal_code = StringField('Postal Code', validators=[DataRequired(), Length(max=20)])
    country = StringField('Country', validators=[Optional(), Length(max=50)], default='USA')
    
    # Lot details
    manager_id = SelectField('Manager', coerce=int, validators=[Optional()])
    hourly_rate = FloatField('Hourly Rate ($)', validators=[DataRequired()])
    daily_rate = FloatField('Daily Rate ($)', validators=[Optional()])
    monthly_rate = FloatField('Monthly Rate ($)', validators=[Optional()])
    opening_time = TimeField('Opening Time', validators=[DataRequired()], default=datetime.strptime('06:00', '%H:%M').time())
    closing_time = TimeField('Closing Time', validators=[DataRequired()], default=datetime.strptime('23:00', '%H:%M').time())
    spot_count = IntegerField('Number of Spots', validators=[Optional()], default=0)
    is_active = BooleanField('Active Lot', default=True)
    submit = SubmitField('Save Lot')
    
    def set_manager_choices(self, managers):
        """Set manager choices for the select field."""
        self.manager_id.choices = [(0, 'No Manager')] + [(m.id, f"{m.first_name} {m.last_name} ({m.email})") for m in managers]


class ProfileForm(FlaskForm):
    """Form for updating user profile information."""
    first_name = StringField('First Name', validators=[DataRequired(), Length(max=50)])
    last_name = StringField('Last Name', validators=[DataRequired(), Length(max=50)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    phone_number = StringField('Phone Number', validators=[Optional(), Length(max=20)])
    submit = SubmitField('Update Profile')


class ChangePasswordForm(FlaskForm):
    """Form for changing user password."""
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[
        DataRequired(), 
        Length(min=6, message='Password must be at least 6 characters long')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('new_password', message='Passwords must match')
    ])
    submit = SubmitField('Change Password')


class ParkingSpotForm(FlaskForm):
    """Form for creating/editing parking spots."""
    spot_number = StringField('Spot Number', validators=[DataRequired(), Length(max=10)])
    spot_type = SelectField('Spot Type', 
                          choices=[
                              ('regular', 'Regular'),
                              ('compact', 'Compact'),
                              ('handicap', 'Handicap'),
                              ('ev', 'Electric Vehicle'),
                              ('motorcycle', 'Motorcycle')
                          ],
                          validators=[DataRequired()])
    is_available = BooleanField('Available', default=True)
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=200)])
    submit = SubmitField('Save Spot')


class PaymentForm(FlaskForm):
    """Form for processing payments."""
    # Payment method selection
    payment_method = SelectField('Payment Method', 
                               choices=[
                                   ('credit_card', 'Credit Card'),
                                   ('debit_card', 'Debit Card'),
                                   ('paypal', 'PayPal'),
                                   ('apple_pay', 'Apple Pay'),
                                   ('google_pay', 'Google Pay')
                               ],
                               validators=[DataRequired()])
    
    # Credit card information (for Stripe)
    card_number = StringField('Card Number', validators=[Optional(), Length(min=13, max=19)])
    expiry_month = SelectField('Expiry Month', 
                             choices=[(str(i).zfill(2), str(i).zfill(2)) for i in range(1, 13)],
                             validators=[Optional()])
    expiry_year = SelectField('Expiry Year', 
                            choices=[(str(i), str(i)) for i in range(2024, 2035)],
                            validators=[Optional()])
    cvv = StringField('CVV', validators=[Optional(), Length(min=3, max=4)])
    
    # Billing information
    billing_name = StringField('Name on Card', validators=[Optional(), Length(max=100)])
    billing_email = StringField('Email', validators=[Optional(), Email()])
    billing_address = StringField('Billing Address', validators=[Optional(), Length(max=200)])
    billing_city = StringField('City', validators=[Optional(), Length(max=100)])
    billing_state = StringField('State', validators=[Optional(), Length(max=50)])
    billing_zip = StringField('ZIP Code', validators=[Optional(), Length(max=10)])
    
    # Terms and conditions
    accept_terms = BooleanField('I accept the terms and conditions', validators=[DataRequired()])
    
    # Hidden fields for booking information
    booking_id = StringField('Booking ID', validators=[Optional()])
    amount = StringField('Amount', validators=[Optional()])
    
    submit = SubmitField('Process Payment')
    
    def validate_card_number(self, field):
        """Validate credit card number format."""
        if self.payment_method.data in ['credit_card', 'debit_card']:
            if not field.data:
                raise ValidationError('Card number is required for card payments.')
            # Remove spaces and validate length
            card_num = field.data.replace(' ', '')
            if not card_num.isdigit() or len(card_num) < 13 or len(card_num) > 19:
                raise ValidationError('Please enter a valid card number.')
    
    def validate_cvv(self, field):
        """Validate CVV format."""
        if self.payment_method.data in ['credit_card', 'debit_card']:
            if not field.data:
                raise ValidationError('CVV is required for card payments.')
            if not field.data.isdigit() or len(field.data) < 3 or len(field.data) > 4:
                raise ValidationError('Please enter a valid CVV.')
    
    def validate_billing_name(self, field):
        """Validate billing name for card payments."""
        if self.payment_method.data in ['credit_card', 'debit_card']:
            if not field.data:
                raise ValidationError('Name on card is required for card payments.')


class BookingPaymentForm(FlaskForm):
    """Combined form for booking and payment in one step."""
    # Booking fields
    parking_spot_id = SelectField('Parking Spot', coerce=int, validators=[DataRequired()])
    vehicle_plate = StringField('Vehicle Plate', validators=[DataRequired(), Length(max=20)])
    start_time = DateTimeLocalField('Start Time', validators=[DataRequired()])
    duration = SelectField('Duration (hours)', coerce=int, validators=[DataRequired()])
    
    # Payment fields
    payment_method = SelectField('Payment Method', 
                               choices=[
                                   ('credit_card', 'Credit Card'),
                                   ('debit_card', 'Debit Card'),
                                   ('paypal', 'PayPal')
                               ],
                               validators=[DataRequired()])
    
    # Card information (shown/hidden based on payment method)
    card_number = StringField('Card Number', validators=[Optional()])
    expiry_month = SelectField('Month', 
                             choices=[('', 'Month')] + [(str(i).zfill(2), str(i).zfill(2)) for i in range(1, 13)],
                             validators=[Optional()])
    expiry_year = SelectField('Year', 
                            choices=[('', 'Year')] + [(str(i), str(i)) for i in range(2024, 2035)],
                            validators=[Optional()])
    cvv = StringField('CVV', validators=[Optional()])
    
    # Billing information
    billing_name = StringField('Name on Card', validators=[Optional()])
    billing_address = StringField('Billing Address', validators=[Optional()])
    billing_city = StringField('City', validators=[Optional()])
    billing_state = StringField('State', validators=[Optional()])
    billing_zip = StringField('ZIP Code', validators=[Optional()])
    
    # Agreement
    accept_terms = BooleanField('I agree to the terms and conditions and cancellation policy', 
                              validators=[DataRequired()])
    
    submit = SubmitField('Book & Pay Now')
    
    def set_spot_choices(self, spots):
        """Dynamically set parking spot choices."""
        self.parking_spot_id.choices = [(s.id, f"Spot #{s.spot_number} ({s.spot_type}) - ${s.parking_lot.hourly_rate}/hr") for s in spots]
    
    def set_duration_choices(self):
        """Set duration choices."""
        self.duration.choices = [(i, f"{i} hour{'s' if i > 1 else ''}") for i in range(1, 25)]
    
    def validate_start_time(self, field):
        """Validate start time is not in the past."""
        if field.data and field.data < datetime.now():
            raise ValidationError('Start time cannot be in the past.')
    
    def validate_card_fields(self):
        """Validate card fields when card payment is selected."""
        if self.payment_method.data in ['credit_card', 'debit_card']:
            errors = []
            
            if not self.card_number.data:
                errors.append('Card number is required')
            elif not self.card_number.data.replace(' ', '').isdigit():
                errors.append('Invalid card number format')
            
            if not self.expiry_month.data:
                errors.append('Expiry month is required')
            
            if not self.expiry_year.data:
                errors.append('Expiry year is required')
            
            if not self.cvv.data:
                errors.append('CVV is required')
            elif not self.cvv.data.isdigit() or len(self.cvv.data) < 3:
                errors.append('Invalid CVV')
            
            if not self.billing_name.data:
                errors.append('Name on card is required')
            
            return errors
        return []


class RefundRequestForm(FlaskForm):
    """Form for users to request a refund (goes to pending approval)."""
    refund_amount = StringField('Refund Amount ($)', validators=[DataRequired()])
    refund_reason = SelectField('Refund Reason',
                                choices=[
                                    ('user_request', 'User Request'),
                                    ('booking_cancelled', 'Booking Cancelled'),
                                    ('system_error', 'System Error'),
                                    ('duplicate_payment', 'Duplicate Payment'),
                                    ('service_unavailable', 'Service Unavailable'),
                                    ('other', 'Other')
                                ],
                                validators=[DataRequired()])
    refund_notes = TextAreaField('Additional Notes', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Submit Refund Request')

    def validate_refund_amount(self, field):
        """Validate refund amount is positive and numeric."""
        try:
            amount = float(field.data)
            if amount <= 0:
                raise ValidationError('Refund amount must be greater than zero.')
        except ValueError:
            raise ValidationError('Please enter a valid amount.')


class RefundForm(FlaskForm):
    """Form for processing refunds."""
    refund_amount = StringField('Refund Amount ($)', validators=[DataRequired()])
    refund_reason = SelectField('Refund Reason',
                              choices=[
                                  ('user_request', 'User Request'),
                                  ('booking_cancelled', 'Booking Cancelled'),
                                  ('system_error', 'System Error'),
                                  ('duplicate_payment', 'Duplicate Payment'),
                                  ('service_unavailable', 'Service Unavailable'),
                                  ('other', 'Other')
                              ],
                              validators=[DataRequired()])
    refund_notes = TextAreaField('Additional Notes', validators=[Optional(), Length(max=500)])
    notify_user = BooleanField('Send notification to user', default=True)
    submit = SubmitField('Process Refund')
    
    def validate_refund_amount(self, field):
        """Validate refund amount is positive and numeric."""
        try:
            amount = float(field.data)
            if amount <= 0:
                raise ValidationError('Refund amount must be greater than zero.')
        except ValueError:
            raise ValidationError('Please enter a valid amount.')
