from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from datetime import timedelta
from app.forms import ProfileForm, ChangePasswordForm
from app.models.user import User
from app import db

# User blueprint
user_bp = Blueprint('user', __name__)

@user_bp.route('/dashboard')
@login_required
def dashboard():
    """User dashboard page."""
    from datetime import datetime
    
    # Get user's bookings
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.created_at.desc()).all()
    
    # Filter active bookings (only confirmed bookings that are ongoing)
    now = datetime.now()
    active_bookings = [b for b in bookings if b.status == 'confirmed' and b.start_time <= now <= b.end_time]
    # Upcoming bookings are confirmed bookings that start in the future
    upcoming_bookings = [b for b in bookings if b.status == 'confirmed' and b.start_time > now]
    # Pending bookings await manager approval
    pending_bookings = [b for b in bookings if b.status == 'pending']
    
    # Calculate total spent (all bookings)
    total_spent = sum(float(b.total_amount or 0) for b in bookings)
    
    return render_template('user/dashboard.html', 
                         user=current_user,
                         active_bookings=active_bookings,
                         upcoming_bookings=upcoming_bookings,
                         pending_bookings=pending_bookings,
                         total_spent=total_spent,
                         bookings=bookings)

# ---------------------- Parking Browsing ----------------------

from app.models.parking import ParkingLot, ParkingSpot, Booking
from app.forms import BookingForm
from app import db

@user_bp.route('/parking')
@login_required
def parking_list():
    lots = ParkingLot.query.all()
    return render_template('parking/list.html', lots=lots)

@user_bp.route('/parking/<int:lot_id>', methods=['GET', 'POST'])
@login_required
def parking_detail(lot_id):
    lot = ParkingLot.query.get_or_404(lot_id)
    available_spots = [s for s in lot.spots if s.is_available]
    form = BookingForm()
    form.set_spot_choices(available_spots)
    form.set_duration_choices()

    if form.validate_on_submit():
        spot = ParkingSpot.query.get(form.parking_spot_id.data)
        # Calculate end time based on duration
        duration_hours = form.duration.data
        end_time = form.start_time.data + timedelta(hours=duration_hours)
        total_amount = float(lot.hourly_rate) * duration_hours
        booking = Booking(
            user_id=current_user.id,
            spot_id=spot.id,
            start_time=form.start_time.data,
            end_time=end_time,
            vehicle_plate=form.vehicle_plate.data,
            status=Booking.STATUS_PENDING,
            total_amount=total_amount
        )
        db.session.add(booking)
        db.session.commit()
        
        # Redirect to payment page for immediate payment
        flash('Booking created! Please complete payment to confirm your reservation.', 'info')
        return redirect(url_for('payment.process_payment', booking_id=booking.id))

    return render_template('parking/detail.html', lot=lot, form=form, available_spots=available_spots)

# ---------------------- Booking Views ----------------------

@user_bp.route('/booking')
@login_required
def booking_list():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.created_at.desc()).all()
    return render_template('booking/list.html', bookings=bookings)

@user_bp.route('/booking/<int:booking_id>')
@login_required
def booking_detail(booking_id):
    booking = Booking.query.filter_by(id=booking_id, user_id=current_user.id).first_or_404()
    # Find completed payment for this booking, if any
    from app.models.parking import Payment
    payment = Payment.query.filter_by(booking_id=booking.id, status=Payment.STATUS_COMPLETED).first()
    return render_template('booking/detail.html', booking=booking, payment=payment)

@user_bp.route('/booking/<int:booking_id>/cancel')
@login_required
def cancel_booking(booking_id):
    booking = Booking.query.filter_by(id=booking_id, user_id=current_user.id).first_or_404()
    
    # Check if booking can be cancelled (not already cancelled or completed)
    if booking.status in ['cancelled', 'completed']:
        flash(f'Booking cannot be cancelled as it is already {booking.status}.', 'warning')
        return redirect(url_for('user.booking_detail', booking_id=booking.id))
    
    # Update booking status to cancelled
    booking.status = 'cancelled'
    db.session.commit()
    
    flash('Booking has been successfully cancelled.', 'success')
    return redirect(url_for('user.booking_list'))


# ---------------------- Profile & Settings ----------------------

@user_bp.route('/profile')
@login_required
def profile():
    """User profile page."""
    return render_template('user/profile.html')


@user_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Edit user profile information."""
    form = ProfileForm()
    
    if form.validate_on_submit():
        try:
            # Check if email is already taken by another user
            existing_user = User.query.filter(
                User.email == form.email.data,
                User.id != current_user.id
            ).first()
            
            if existing_user:
                flash('Email address is already in use by another user.', 'danger')
                return render_template('user/edit_profile.html', form=form)
            
            # Update user information
            current_user.first_name = form.first_name.data
            current_user.last_name = form.last_name.data
            current_user.email = form.email.data
            current_user.phone_number = form.phone_number.data
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('user.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'danger')
    
    # Pre-populate form with current user data
    if request.method == 'GET':
        form.first_name.data = current_user.first_name
        form.last_name.data = current_user.last_name
        form.email.data = current_user.email
        form.phone_number.data = current_user.phone_number
    
    return render_template('user/edit_profile.html', form=form)


@user_bp.route('/settings')
@login_required
def settings():
    """User settings page."""
    return render_template('user/settings.html')


@user_bp.route('/deactivate', methods=['GET', 'POST'])
@login_required
def deactivate_account():
    """Allow a user to deactivate (soft-delete) their own account."""
    if request.method == 'POST':
        try:
            current_user.is_active = False
            db.session.commit()
            from flask_login import logout_user
            logout_user()
            flash('Your account has been deactivated. You can contact support to reactivate it.', 'info')
            return redirect(url_for('main.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error deactivating account: {str(e)}', 'danger')
            return redirect(url_for('user.settings'))

    # GET request -> show confirmation page
    return render_template('user/deactivate_confirm.html')


@user_bp.route('/settings/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change user password."""
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        try:
            # Verify current password
            if not current_user.check_password(form.current_password.data):
                flash('Current password is incorrect.', 'danger')
                return render_template('user/change_password.html', form=form)
            
            # Update password
            current_user.set_password(form.new_password.data)
            db.session.commit()
            
            flash('Password changed successfully!', 'success')
            return redirect(url_for('user.settings'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error changing password: {str(e)}', 'danger')
    
    return render_template('user/change_password.html', form=form)
