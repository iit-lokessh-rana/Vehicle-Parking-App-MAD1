from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models.parking import ParkingLot, Booking, ParkingSpot, Payment
from app.models.user import User
from app.forms import BookingForm, ProfileForm, ChangePasswordForm, ParkingSpotForm, UserForm

# Manager blueprint
manager_bp = Blueprint('manager', __name__, url_prefix='/manager')

def manager_required(f):
    """Decorator to ensure user is a manager of at least one parking lot."""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        
        # Check if user is a manager of any parking lot
        managed_lots = ParkingLot.query.filter_by(manager_id=current_user.id).all()
        if not managed_lots and not current_user.is_admin:
            flash('You do not have manager permissions.', 'danger')
            return redirect(url_for('user.dashboard'))
        
        return f(*args, **kwargs)
    return decorated_function

@manager_bp.route('/')
@manager_bp.route('/dashboard')
@login_required
@manager_required
def dashboard():
    """Manager dashboard showing pending bookings for their lots."""
    # Get parking lots managed by current user
    if current_user.is_admin:
        # Admin can see all lots
        managed_lots = ParkingLot.query.all()
    else:
        managed_lots = ParkingLot.query.filter_by(manager_id=current_user.id).all()
    
    if not managed_lots:
        flash('No parking lots assigned to you.', 'info')
        return redirect(url_for('user.dashboard'))
    
    # Get pending bookings for managed lots
    lot_ids = [lot.id for lot in managed_lots]
    from app.models.parking import ParkingSpot
    pending_bookings = (Booking.query
                       .join(ParkingSpot, Booking.spot_id == ParkingSpot.id)
                       .filter(ParkingSpot.parking_lot_id.in_(lot_ids))
                       .filter(Booking.status == Booking.STATUS_PENDING)
                       .order_by(Booking.created_at.desc())
                       .all())
    
    # Get recent approved/rejected bookings for context
    recent_bookings = (Booking.query
                      .join(ParkingSpot, Booking.spot_id == ParkingSpot.id)
                      .filter(ParkingSpot.parking_lot_id.in_(lot_ids))
                      .filter(Booking.status.in_([Booking.STATUS_CONFIRMED, Booking.STATUS_CANCELLED]))
                      .order_by(Booking.updated_at.desc())
                      .limit(10)
                      .all())
    
    return render_template('manager/dashboard.html', 
                         managed_lots=managed_lots,
                         pending_bookings=pending_bookings,
                         recent_bookings=recent_bookings)

@manager_bp.route('/booking/<int:booking_id>')
@login_required
@manager_required
def booking_detail(booking_id):
    """View detailed information about a booking for approval."""
    booking = Booking.query.get_or_404(booking_id)
    
    # Ensure manager has permission to view this booking
    if not current_user.is_admin:
        managed_lot_ids = [lot.id for lot in ParkingLot.query.filter_by(manager_id=current_user.id).all()]
        if booking.spot.parking_lot.id not in managed_lot_ids:
            flash('You do not have permission to view this booking.', 'danger')
            return redirect(url_for('manager.dashboard'))
    
    return render_template('manager/booking_detail.html', booking=booking)

@manager_bp.route('/booking/<int:booking_id>/approve', methods=['POST'])
@login_required
@manager_required
def approve_booking(booking_id):
    """Approve a pending booking."""
    booking = Booking.query.get_or_404(booking_id)
    
    # Ensure manager has permission to approve this booking
    if not current_user.is_admin:
        managed_lot_ids = [lot.id for lot in ParkingLot.query.filter_by(manager_id=current_user.id).all()]
        if booking.spot.parking_lot.id not in managed_lot_ids:
            flash('You do not have permission to approve this booking.', 'danger')
            return redirect(url_for('manager.dashboard'))
    
    # Check if booking is still pending
    if booking.status != Booking.STATUS_PENDING:
        flash(f'Booking is already {booking.status} and cannot be approved.', 'warning')
        return redirect(url_for('manager.booking_detail', booking_id=booking.id))
    
    # Check for conflicts with other confirmed bookings
    conflicting_bookings = (Booking.query
                           .filter(Booking.spot_id == booking.spot_id)
                           .filter(Booking.status == Booking.STATUS_CONFIRMED)
                           .filter(
                               db.or_(
                                   db.and_(Booking.start_time <= booking.start_time, Booking.end_time > booking.start_time),
                                   db.and_(Booking.start_time < booking.end_time, Booking.end_time >= booking.end_time),
                                   db.and_(Booking.start_time >= booking.start_time, Booking.end_time <= booking.end_time)
                               )
                           )
                           .first())
    
    if conflicting_bookings:
        flash('Cannot approve booking due to time conflict with another confirmed booking.', 'danger')
        return redirect(url_for('manager.booking_detail', booking_id=booking.id))
    
    # Approve the booking
    booking.status = Booking.STATUS_CONFIRMED
    booking.notes = request.form.get('approval_notes', '').strip()
    db.session.commit()
    
    flash(f'Booking #{booking.id} has been approved successfully.', 'success')
    return redirect(url_for('manager.dashboard'))

@manager_bp.route('/booking/<int:booking_id>/reject', methods=['POST'])
@login_required
@manager_required
def reject_booking(booking_id):
    """Reject a pending booking."""
    booking = Booking.query.get_or_404(booking_id)
    
    # Ensure manager has permission to reject this booking
    if not current_user.is_admin:
        managed_lot_ids = [lot.id for lot in ParkingLot.query.filter_by(manager_id=current_user.id).all()]
        if booking.spot.parking_lot.id not in managed_lot_ids:
            flash('You do not have permission to reject this booking.', 'danger')
            return redirect(url_for('manager.dashboard'))
    
    # Check if booking is still pending
    if booking.status != Booking.STATUS_PENDING:
        flash(f'Booking is already {booking.status} and cannot be rejected.', 'warning')
        return redirect(url_for('manager.booking_detail', booking_id=booking.id))
    
    # Reject the booking
    booking.status = Booking.STATUS_CANCELLED
    booking.cancellation_reason = Booking.CANCELLATION_OTHER
    rejection_reason = request.form.get('rejection_reason', '').strip()
    booking.cancellation_notes = rejection_reason if rejection_reason else 'Rejected by manager'
    db.session.commit()
    
    flash(f'Booking #{booking.id} has been rejected.', 'info')
    return redirect(url_for('manager.dashboard'))

@manager_bp.route('/lots')
@login_required
@manager_required
def managed_lots():
    """View all parking lots managed by the current user."""
    if current_user.is_admin:
        managed_lots = ParkingLot.query.all()
    else:
        managed_lots = ParkingLot.query.filter_by(manager_id=current_user.id).all()
    
    return render_template('manager/lots.html', managed_lots=managed_lots)

@manager_bp.route('/lots/<int:lot_id>')
@login_required
@manager_required
def lot_detail(lot_id):
    """View detailed information about a parking lot."""
    lot = ParkingLot.query.get_or_404(lot_id)
    
    # Ensure manager has permission to view this lot
    if not current_user.is_admin and lot.manager_id != current_user.id:
        flash('You do not have permission to manage this lot.', 'danger')
        return redirect(url_for('manager.managed_lots'))
    
    # Get lot statistics
    from sqlalchemy import func, and_
    from datetime import datetime, timedelta
    
    total_bookings = Booking.query.join(ParkingSpot).filter(ParkingSpot.parking_lot_id == lot.id).count()
    pending_bookings = (Booking.query
                       .join(ParkingSpot)
                       .filter(ParkingSpot.parking_lot_id == lot.id)
                       .filter(Booking.status == Booking.STATUS_PENDING)
                       .count())
    
    # Monthly revenue
    start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_revenue = db.session.query(func.sum(Booking.total_amount)).join(ParkingSpot).filter(
        and_(
            ParkingSpot.parking_lot_id == lot.id,
            Booking.status.in_(['confirmed', 'completed']),
            Booking.created_at >= start_of_month
        )
    ).scalar() or 0
    
    # Recent bookings
    recent_bookings = (Booking.query
                      .join(ParkingSpot)
                      .filter(ParkingSpot.parking_lot_id == lot.id)
                      .order_by(Booking.created_at.desc())
                      .limit(10)
                      .all())
    
    return render_template('manager/lot_detail.html',
                         lot=lot,
                         total_bookings=total_bookings,
                         pending_bookings=pending_bookings,
                         monthly_revenue=monthly_revenue,
                         recent_bookings=recent_bookings)

@manager_bp.route('/lots/<int:lot_id>/toggle-status', methods=['POST'])
@login_required
@manager_required
def toggle_lot_status(lot_id):
    """Toggle parking lot active/inactive status."""
    lot = ParkingLot.query.get_or_404(lot_id)
    
    # Ensure manager has permission to manage this lot
    if not current_user.is_admin and lot.manager_id != current_user.id:
        flash('You do not have permission to manage this lot.', 'danger')
        return redirect(url_for('manager.managed_lots'))
    
    lot.is_active = not lot.is_active
    db.session.commit()
    
    status = 'activated' if lot.is_active else 'deactivated'
    flash(f'Parking lot "{lot.name}" has been {status}.', 'success')
    
    return redirect(url_for('manager.lot_detail', lot_id=lot.id))

@manager_bp.route('/lots/<int:lot_id>/spots')
@login_required
@manager_required
def lot_spots(lot_id):
    """Manage individual parking spots for a lot."""
    lot = ParkingLot.query.get_or_404(lot_id)
    
    # Ensure manager has permission to manage this lot
    if not current_user.is_admin and lot.manager_id != current_user.id:
        flash('You do not have permission to manage this lot.', 'danger')
        return redirect(url_for('manager.managed_lots'))
    
    spots = ParkingSpot.query.filter_by(parking_lot_id=lot.id).order_by(ParkingSpot.spot_number).all()
    
    return render_template('manager/lot_spots.html', lot=lot, spots=spots)


@manager_bp.route('/lots/<int:lot_id>/spots/add', methods=['GET', 'POST'])
@login_required
@manager_required
def add_spot(lot_id):
    """Add a new parking spot to a lot."""
    lot = ParkingLot.query.get_or_404(lot_id)
    
    # Ensure manager has permission to manage this lot
    if not current_user.is_admin and lot.manager_id != current_user.id:
        flash('You do not have permission to manage this lot.', 'danger')
        return redirect(url_for('manager.managed_lots'))
    
    form = ParkingSpotForm()
    
    if form.validate_on_submit():
        try:
            # Check if spot number already exists in this lot
            existing_spot = ParkingSpot.query.filter_by(
                parking_lot_id=lot.id,
                spot_number=form.spot_number.data
            ).first()
            
            if existing_spot:
                flash(f'Spot {form.spot_number.data} already exists in this lot.', 'danger')
            else:
                spot = ParkingSpot(
                    spot_number=form.spot_number.data,
                    spot_type=form.spot_type.data,
                    is_available=form.is_available.data,
                    notes=form.notes.data,
                    parking_lot_id=lot.id
                )
                db.session.add(spot)
                db.session.commit()
                flash(f'Spot {spot.spot_number} added successfully!', 'success')
                return redirect(url_for('manager.lot_spots', lot_id=lot.id))
                
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while adding the spot. Please try again.', 'danger')
            
    return render_template('manager/add_spot.html', lot=lot, form=form)

@manager_bp.route('/spots/<int:spot_id>/toggle-availability', methods=['POST'])
@login_required
@manager_required
def toggle_spot_availability(spot_id):
    """Toggle individual spot availability."""
    from app.models.parking import ParkingSpot
    spot = ParkingSpot.query.get_or_404(spot_id)
    
    # Ensure manager has permission to manage this spot's lot
    if not current_user.is_admin and spot.parking_lot.manager_id != current_user.id:
        flash('You do not have permission to manage this spot.', 'danger')
        return redirect(url_for('manager.managed_lots'))
    
    # Check if spot has active bookings
    active_bookings = (Booking.query
                      .filter(Booking.spot_id == spot.id)
                      .filter(Booking.status.in_(['confirmed', 'checked_in']))
                      .filter(Booking.end_time > datetime.now())
                      .count())
    
    if active_bookings > 0 and spot.is_available:
        flash('Cannot disable spot with active bookings.', 'warning')
        return redirect(url_for('manager.lot_spots', lot_id=spot.parking_lot_id))
    
    spot.is_available = not spot.is_available
    
    # Update lot's available spot count
    if spot.is_available:
        spot.parking_lot.available_spots += 1
    else:
        spot.parking_lot.available_spots -= 1
    
    db.session.commit()
    
    status = 'enabled' if spot.is_available else 'disabled'
    flash(f'Spot #{spot.spot_number} has been {status}.', 'success')
    
    return redirect(url_for('manager.lot_spots', lot_id=spot.parking_lot_id))

@manager_bp.route('/lots/<int:lot_id>/edit', methods=['GET', 'POST'])
@login_required
@manager_required
def edit_lot(lot_id):
    """Edit parking lot details (managers can edit basic info)."""
    lot = ParkingLot.query.get_or_404(lot_id)
    
    # Ensure manager has permission to manage this lot
    if not current_user.is_admin and lot.manager_id != current_user.id:
        flash('You do not have permission to edit this lot.', 'danger')
        return redirect(url_for('manager.managed_lots'))
    
    if request.method == 'POST':
        # Managers can only edit basic lot information
        lot.description = request.form.get('description', '').strip()
        lot.hourly_rate = float(request.form.get('hourly_rate', lot.hourly_rate))
        lot.daily_rate = float(request.form.get('daily_rate', 0)) if request.form.get('daily_rate') else None
        lot.monthly_rate = float(request.form.get('monthly_rate', 0)) if request.form.get('monthly_rate') else None
        
        from datetime import datetime
        lot.opening_time = datetime.strptime(request.form.get('opening_time', '06:00'), '%H:%M').time()
        lot.closing_time = datetime.strptime(request.form.get('closing_time', '23:00'), '%H:%M').time()
        
        try:
            db.session.commit()
            flash(f'Parking lot "{lot.name}" updated successfully.', 'success')
            return redirect(url_for('manager.lot_detail', lot_id=lot.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating parking lot: {str(e)}', 'danger')
    
    return render_template('manager/edit_lot.html', lot=lot)


@manager_bp.route('/profile')
@login_required
@manager_required
def profile():
    """Manager profile page."""
    return render_template('manager/profile.html')


@manager_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
@manager_required
def edit_profile():
    """Edit manager profile information."""
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
                return render_template('manager/edit_profile.html', form=form)
            
            # Update user information
            current_user.first_name = form.first_name.data
            current_user.last_name = form.last_name.data
            current_user.email = form.email.data
            current_user.phone_number = form.phone_number.data
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('manager.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'danger')
    
    # Pre-populate form with current user data
    if request.method == 'GET':
        form.first_name.data = current_user.first_name
        form.last_name.data = current_user.last_name
        form.email.data = current_user.email
        form.phone_number.data = current_user.phone_number
    
    return render_template('manager/edit_profile.html', form=form)


@manager_bp.route('/settings')
@login_required
@manager_required
def settings():
    """Manager settings page."""
    return render_template('manager/settings.html')



@manager_bp.route('/users/new', methods=['GET', 'POST'])
@login_required
@manager_required
def create_user():
    """Create a regular end user (vehicle owner) from manager dashboard."""
    form = UserForm()

    # Managers can only create regular users (non-admin, non-manager)
    form.is_admin.render_kw = {'disabled': True}

    if form.validate_on_submit():
        # Prevent manager from elevating privileges via request tampering
        is_admin = False
        try:
            # Check unique email
            from app.models.user import User
            if User.query.filter_by(email=form.email.data).first():
                flash('Email is already registered.', 'danger')
                return render_template('manager/create_user.html', form=form)

            user = User(
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                email=form.email.data,
                phone_number=form.phone_number.data,
                is_admin=is_admin,
                is_active=form.is_active.data
            )
            if form.password.data:
                user.set_password(form.password.data)
            else:
                user.set_password('password')  # default temp password

            db.session.add(user)
            db.session.commit()
            flash('User created successfully!', 'success')
            return redirect(url_for('manager.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')

    return render_template('manager/create_user.html', form=form)


@manager_bp.route('/settings/change-password', methods=['GET', 'POST'])
@login_required
@manager_required
def change_password():
    """Change manager password."""
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        try:
            # Verify current password
            if not current_user.check_password(form.current_password.data):
                flash('Current password is incorrect.', 'danger')
                return render_template('manager/change_password.html', form=form)
            
            # Update password
            current_user.set_password(form.new_password.data)
            db.session.commit()
            
            flash('Password changed successfully!', 'success')
            return redirect(url_for('manager.settings'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error changing password: {str(e)}', 'danger')
    
    return render_template('manager/change_password.html', form=form)
# ===================== USER ACCOUNT STATUS =====================
@manager_bp.route('/users')
@login_required
@manager_required
def list_users():
    """List all regular end users for manager."""
    users = User.query.filter_by(is_admin=False).all()
    return render_template('manager/users.html', users=users)

# ===================== REFUND REQUESTS =====================
@manager_bp.route('/refund-requests')
@login_required
@manager_required
def refund_requests():
    """List pending refund requests for lots managed by current user."""
    from app.models.refund import RefundRequest
    from app.models.parking import ParkingSpot
    # Determine lots the manager oversees (admins see all)
    if current_user.is_admin:
        pending = RefundRequest.query.filter_by(status=RefundRequest.STATUS_PENDING).order_by(RefundRequest.created_at.desc()).all()
    else:
        lot_ids = [lot.id for lot in ParkingLot.query.filter_by(manager_id=current_user.id).all()]
        pending = (RefundRequest.query.join(Payment)
                   .join(Booking)
                   .join(ParkingSpot, Booking.spot_id == ParkingSpot.id)
                   .filter(ParkingSpot.parking_lot_id.in_(lot_ids))
                   .filter(RefundRequest.status == RefundRequest.STATUS_PENDING)
                   .order_by(RefundRequest.created_at.desc())
                   .all())
    return render_template('manager/refund_requests.html', pending_requests=pending)


@manager_bp.route('/refund-requests/<int:request_id>/approve', methods=['POST'])
@login_required
@manager_required
def approve_refund_request(request_id):
    """Approve a refund request, process Stripe refund, update records."""
    from app.models.refund import RefundRequest
    req = RefundRequest.query.get_or_404(request_id)
    # Permission check like above
    if not current_user.is_admin:
        lot_ids = [lot.id for lot in ParkingLot.query.filter_by(manager_id=current_user.id).all()]
        if req.payment.booking.spot.parking_lot_id not in lot_ids:
            flash('You do not have permission to approve this refund.', 'danger')
            return redirect(url_for('manager.refund_requests'))
    if req.status != RefundRequest.STATUS_PENDING:
        flash('Refund request already processed.', 'info')
        return redirect(url_for('manager.refund_requests'))
    # Process refund via helper
    remaining_cents = int(float(req.requested_amount) * 100)
    success, result = process_stripe_refund(req.payment.gateway_payment_intent_id, remaining_cents, reason=req.reason)
    if success:
        try:
            req.payment.refunded_amount = (req.payment.refunded_amount or 0) + float(req.requested_amount)
            if req.payment.refunded_amount >= req.payment.amount:
                req.payment.booking.status = 'cancelled'
            req.payment.refund_reference = result.get('id')
            req.mark_approved(current_user.id)
            db.session.commit()
            flash('Refund approved and processed successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating records: {str(e)}', 'danger')
    else:
        flash(f'Refund processing failed: {result.get("error", "unknown error")}', 'danger')
    return redirect(url_for('manager.refund_requests'))


@manager_bp.route('/refund-requests/<int:request_id>/deny', methods=['POST'])
@login_required
@manager_required
def deny_refund_request(request_id):
    from app.models.refund import RefundRequest
    req = RefundRequest.query.get_or_404(request_id)
    # Permission check same as approve
    if not current_user.is_admin:
        lot_ids = [lot.id for lot in ParkingLot.query.filter_by(manager_id=current_user.id).all()]
        if req.payment.booking.spot.parking_lot_id not in lot_ids:
            flash('You do not have permission to deny this refund.', 'danger')
            return redirect(url_for('manager.refund_requests'))
    if req.status != RefundRequest.STATUS_PENDING:
        flash('Refund request already processed.', 'info')
        return redirect(url_for('manager.refund_requests'))
    req.mark_denied(current_user.id)
    db.session.commit()
    flash('Refund request denied.', 'success')
    return redirect(url_for('manager.refund_requests'))

# ===================== USER ACCOUNT STATUS =====================
@manager_bp.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@manager_required
def toggle_user_status(user_id):
    """Toggle active status of a regular (driver) user by the manager."""
    from flask import request

    user = User.query.get_or_404(user_id)

    # Managers cannot modify admins or other managers
    if user.is_admin or user.managed_lots:
        flash('You do not have permission to modify this account.', 'danger')
        return redirect(request.referrer or url_for('manager.dashboard'))

    # Prevent self-deactivation
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'warning')
        return redirect(request.referrer or url_for('manager.dashboard'))

    try:
        user.is_active = not user.is_active
        db.session.commit()
        status = 'activated' if user.is_active else 'deactivated'
        flash(f'User {user.full_name} has been {status}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating user status: {str(e)}', 'danger')

    return redirect(request.referrer or url_for('manager.dashboard'))
