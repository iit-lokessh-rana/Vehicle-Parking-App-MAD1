from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta
from app import db
from app.models.user import User
from app.models.parking import ParkingLot, ParkingSpot, Booking, Transaction, Complaint, Address
from app.forms import ParkingLotForm, UserForm, ProfileForm, ChangePasswordForm

# Admin blueprint
admin = Blueprint('admin', __name__)

def admin_required(f):
    """Decorator to ensure user is admin."""
    from functools import wraps
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('user.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

@admin.route('/')
@admin.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard with system overview."""
    # Get system statistics
    total_users = User.query.count()
    total_lots = ParkingLot.query.count()
    total_spots = ParkingSpot.query.count()
    total_bookings = Booking.query.count()
    
    # Recent activity
    recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(5).all()
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    
    # Revenue statistics
    total_revenue = db.session.query(func.sum(Booking.total_amount)).filter(
        Booking.status.in_(['confirmed', 'completed'])
    ).scalar() or 0
    
    # This month's revenue
    start_of_month = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_revenue = db.session.query(func.sum(Booking.total_amount)).filter(
        and_(
            Booking.status.in_(['confirmed', 'completed']),
            Booking.created_at >= start_of_month
        )
    ).scalar() or 0
    
    return render_template('admin/dashboard.html',
                         total_users=total_users,
                         total_lots=total_lots,
                         total_spots=total_spots,
                         total_bookings=total_bookings,
                         total_revenue=total_revenue,
                         monthly_revenue=monthly_revenue,
                         recent_bookings=recent_bookings,
                         recent_users=recent_users)

# ===================== USER MANAGEMENT =====================

@admin.route('/users')
@login_required
@admin_required
def users():
    """List all users with search and filter capabilities."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    
    query = User.query
    
    # Apply search filter
    if search:
        query = query.filter(
            or_(
                User.first_name.ilike(f'%{search}%'),
                User.last_name.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%')
            )
        )
    
    # Apply role filter
    if role_filter == 'admin':
        query = query.filter(User.is_admin == True)
    elif role_filter == 'manager':
        query = query.join(ParkingLot, User.id == ParkingLot.manager_id, isouter=True).filter(ParkingLot.id.isnot(None))
    elif role_filter == 'user':
        query = query.filter(User.is_admin == False)
    
    users = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/users.html', users=users, search=search, role_filter=role_filter)

@admin.route('/users/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    """View detailed information about a specific user."""
    user = User.query.get_or_404(user_id)
    
    # Get user's booking statistics
    total_bookings = Booking.query.filter_by(user_id=user.id).count()
    total_spent = db.session.query(func.sum(Booking.total_amount)).filter(
        and_(Booking.user_id == user.id, Booking.status.in_(['confirmed', 'completed']))
    ).scalar() or 0
    
    # Get recent bookings
    recent_bookings = Booking.query.filter_by(user_id=user.id).order_by(Booking.created_at.desc()).limit(10).all()
    
    # Get managed lots if user is a manager
    managed_lots = ParkingLot.query.filter_by(manager_id=user.id).all()
    
    return render_template('admin/user_detail.html', 
                         user=user,
                         total_bookings=total_bookings,
                         total_spent=total_spent,
                         recent_bookings=recent_bookings,
                         managed_lots=managed_lots)

@admin.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit user information."""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        user.first_name = request.form.get('first_name', '').strip()
        user.last_name = request.form.get('last_name', '').strip()
        user.email = request.form.get('email', '').strip()
        user.phone_number = request.form.get('phone_number', '').strip()
        user.is_admin = 'is_admin' in request.form
        user.is_active = 'is_active' in request.form
        
        # Update password if provided
        new_password = request.form.get('password', '').strip()
        if new_password:
            user.set_password(new_password)
        
        try:
            db.session.commit()
            flash(f'User {user.full_name} updated successfully.', 'success')
            return redirect(url_for('admin.user_detail', user_id=user.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {str(e)}', 'danger')
    
    return render_template('admin/edit_user.html', user=user)

@admin.route('/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    """Create a new user."""
    form = UserForm()
    
    if form.validate_on_submit():
        # Check if email already exists
        existing_user = User.query.filter_by(email=form.email.data).first()
        if existing_user:
            flash('Email already exists.', 'danger')
            return render_template('admin/create_user.html', form=form)
        
        try:
            user = User(
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                email=form.email.data,
                phone_number=form.phone_number.data,
                is_admin=form.is_admin.data,
                is_active=form.is_active.data
            )
            
            if form.password.data:
                user.set_password(form.password.data)
            else:
                flash('Password is required.', 'danger')
                return render_template('admin/create_user.html', form=form)
            
            db.session.add(user)
            db.session.commit()
            flash(f'User {user.full_name} created successfully.', 'success')
            return redirect(url_for('admin.user_detail', user_id=user.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating user: {str(e)}', 'danger')
    
    return render_template('admin/create_user.html', form=form)

@admin.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status(user_id):
    """Toggle user active status."""
    user = User.query.get_or_404(user_id)
    
    # Prevent deactivating the current admin
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'warning')
        return redirect(url_for('admin.user_detail', user_id=user.id))
    
    user.is_active = not user.is_active
    db.session.commit()
    
    status = 'activated' if user.is_active else 'deactivated'
    flash(f'User {user.full_name} has been {status}.', 'success')
    
    return redirect(url_for('admin.user_detail', user_id=user.id))

# ===================== PARKING LOT MANAGEMENT =====================

@admin.route('/lots')
@login_required
@admin_required
def lots():
    """List all parking lots with management options."""
    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '')
    
    query = ParkingLot.query
    
    # Apply search filter
    if search:
        query = query.filter(
            or_(
                ParkingLot.name.ilike(f'%{search}%'),
                ParkingLot.description.ilike(f'%{search}%')
            )
        )
    
    lots = query.order_by(ParkingLot.created_at.desc()).paginate(
        page=page, per_page=15, error_out=False
    )
    
    return render_template('admin/lots.html', lots=lots, search=search)

@admin.route('/lots/<int:lot_id>')
@login_required
@admin_required
def lot_detail(lot_id):
    """View detailed information about a parking lot."""
    lot = ParkingLot.query.get_or_404(lot_id)
    
    # Get lot statistics
    total_bookings = Booking.query.join(ParkingSpot).filter(ParkingSpot.parking_lot_id == lot.id).count()
    total_revenue = db.session.query(func.sum(Booking.total_amount)).join(ParkingSpot).filter(
        and_(
            ParkingSpot.parking_lot_id == lot.id,
            Booking.status.in_(['confirmed', 'completed'])
        )
    ).scalar() or 0
    
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
    
    # Occupancy rate (current)
    occupied_spots = ParkingSpot.query.filter(
        and_(
            ParkingSpot.parking_lot_id == lot.id,
            ParkingSpot.is_available == False
        )
    ).count()
    occupancy_rate = (occupied_spots / lot.total_spots * 100) if lot.total_spots > 0 else 0
    
    return render_template('admin/lot_detail.html',
                         lot=lot,
                         total_bookings=total_bookings,
                         total_revenue=total_revenue,
                         monthly_revenue=monthly_revenue,
                         recent_bookings=recent_bookings,
                         occupancy_rate=occupancy_rate)

@admin.route('/lots/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_lot():
    """Create a new parking lot."""
    if request.method == 'POST':
        # Create address first
        address = Address(
            street=request.form.get('street', '').strip(),
            city=request.form.get('city', '').strip(),
            state=request.form.get('state', '').strip(),
            postal_code=request.form.get('postal_code', '').strip(),
            country=request.form.get('country', 'USA').strip()
        )
        db.session.add(address)
        db.session.flush()  # Get the address ID
        
        # Get manager if specified
        manager_id = request.form.get('manager_id')
        if manager_id and manager_id != '':
            manager_id = int(manager_id)
        else:
            manager_id = None
        
        # Create parking lot
        lot = ParkingLot(
            name=request.form.get('name', '').strip(),
            description=request.form.get('description', '').strip(),
            address_id=address.id,
            manager_id=manager_id,
            hourly_rate=float(request.form.get('hourly_rate', 0)),
            daily_rate=float(request.form.get('daily_rate', 0)) if request.form.get('daily_rate') else None,
            monthly_rate=float(request.form.get('monthly_rate', 0)) if request.form.get('monthly_rate') else None,
            opening_time=datetime.strptime(request.form.get('opening_time', '06:00'), '%H:%M').time(),
            closing_time=datetime.strptime(request.form.get('closing_time', '23:00'), '%H:%M').time(),
            is_active='is_active' in request.form
        )
        
        try:
            db.session.add(lot)
            db.session.commit()
            
            # Create default spots if requested
            spot_count = int(request.form.get('spot_count', 0))
            if spot_count > 0:
                for i in range(1, spot_count + 1):
                    spot = ParkingSpot(
                        spot_number=str(i),
                        floor=1,
                        spot_type=ParkingSpot.TYPE_REGULAR,
                        is_available=True,
                        parking_lot_id=lot.id
                    )
                    db.session.add(spot)
                
                lot.total_spots = spot_count
                lot.available_spots = spot_count
                db.session.commit()
            
            flash(f'Parking lot "{lot.name}" created successfully.', 'success')
            return redirect(url_for('admin.lot_detail', lot_id=lot.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating parking lot: {str(e)}', 'danger')
    
    # Get available managers for assignment
    managers = User.query.filter_by(is_admin=False).all()
    
    return render_template('admin/create_lot.html', managers=managers)

@admin.route('/lots/<int:lot_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_lot(lot_id):
    """Edit parking lot information."""
    lot = ParkingLot.query.get_or_404(lot_id)
    
    if request.method == 'POST':
        # Update address
        lot.address.street = request.form.get('street', '').strip()
        lot.address.city = request.form.get('city', '').strip()
        lot.address.state = request.form.get('state', '').strip()
        lot.address.postal_code = request.form.get('postal_code', '').strip()
        lot.address.country = request.form.get('country', 'USA').strip()
        
        # Update lot details
        lot.name = request.form.get('name', '').strip()
        lot.description = request.form.get('description', '').strip()
        lot.hourly_rate = float(request.form.get('hourly_rate', 0))
        lot.daily_rate = float(request.form.get('daily_rate', 0)) if request.form.get('daily_rate') else None
        lot.monthly_rate = float(request.form.get('monthly_rate', 0)) if request.form.get('monthly_rate') else None
        lot.opening_time = datetime.strptime(request.form.get('opening_time', '06:00'), '%H:%M').time()
        lot.closing_time = datetime.strptime(request.form.get('closing_time', '23:00'), '%H:%M').time()
        lot.is_active = 'is_active' in request.form
        
        # Update manager
        manager_id = request.form.get('manager_id')
        if manager_id and manager_id != '':
            lot.manager_id = int(manager_id)
        else:
            lot.manager_id = None
        
        try:
            db.session.commit()
            flash(f'Parking lot "{lot.name}" updated successfully.', 'success')
            return redirect(url_for('admin.lot_detail', lot_id=lot.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating parking lot: {str(e)}', 'danger')
    
    # Get available managers for assignment
    managers = User.query.filter_by(is_admin=False).all()
    
    return render_template('admin/edit_lot.html', lot=lot, managers=managers)

@admin.route('/lots/<int:lot_id>/toggle-status', methods=['POST'])
@login_required
@admin_required
def toggle_lot_status(lot_id):
    """Toggle parking lot active status."""
    lot = ParkingLot.query.get_or_404(lot_id)
    
    lot.is_active = not lot.is_active
    db.session.commit()
    
    status = 'activated' if lot.is_active else 'deactivated'
    flash(f'Parking lot "{lot.name}" has been {status}.', 'success')
    
    return redirect(url_for('admin.lot_detail', lot_id=lot.id))

# ===================== REVENUE REPORTS & ANALYTICS =====================

@admin.route('/reports')
@login_required
@admin_required
def reports():
    """Revenue reports and analytics dashboard."""
    # Date range filters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    lot_id = request.args.get('lot_id', type=int)
    
    # Default to current month if no dates provided
    if not start_date:
        start_date = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    if not end_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
    
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    # Base query for bookings in date range
    base_query = Booking.query.filter(
        and_(
            Booking.created_at >= start_datetime,
            Booking.created_at <= end_datetime,
            Booking.status.in_(['confirmed', 'completed'])
        )
    )
    
    # Filter by parking lot if specified
    if lot_id:
        base_query = base_query.join(ParkingSpot).filter(ParkingSpot.parking_lot_id == lot_id)
    
    # Total revenue
    total_revenue = db.session.query(func.sum(Booking.total_amount)).filter(
        base_query.whereclause
    ).scalar() or 0
    
    # Total bookings
    total_bookings = base_query.count()
    
    # Average booking value
    avg_booking_value = total_revenue / total_bookings if total_bookings > 0 else 0
    
    # Revenue by parking lot
    revenue_by_lot = db.session.query(
        ParkingLot.name,
        func.sum(Booking.total_amount).label('revenue'),
        func.count(Booking.id).label('bookings')
    ).join(ParkingSpot).join(Booking).filter(
        and_(
            Booking.created_at >= start_datetime,
            Booking.created_at <= end_datetime,
            Booking.status.in_(['confirmed', 'completed'])
        )
    ).group_by(ParkingLot.id, ParkingLot.name).order_by(func.sum(Booking.total_amount).desc()).all()
    
    # Daily revenue trend (last 30 days)
    daily_revenue = db.session.query(
        func.date(Booking.created_at).label('date'),
        func.sum(Booking.total_amount).label('revenue')
    ).filter(
        and_(
            Booking.created_at >= datetime.now() - timedelta(days=30),
            Booking.status.in_(['confirmed', 'completed'])
        )
    ).group_by(func.date(Booking.created_at)).order_by('date').all()
    
    # Top users by spending
    top_users = db.session.query(
        User.first_name,
        User.last_name,
        User.email,
        func.sum(Booking.total_amount).label('total_spent'),
        func.count(Booking.id).label('total_bookings')
    ).join(Booking).filter(
        and_(
            Booking.created_at >= start_datetime,
            Booking.created_at <= end_datetime,
            Booking.status.in_(['confirmed', 'completed'])
        )
    ).group_by(User.id).order_by(func.sum(Booking.total_amount).desc()).limit(10).all()
    
    # Get all parking lots for filter dropdown
    all_lots = ParkingLot.query.order_by(ParkingLot.name).all()
    
    return render_template('admin/reports.html',
                         total_revenue=total_revenue,
                         total_bookings=total_bookings,
                         avg_booking_value=avg_booking_value,
                         revenue_by_lot=revenue_by_lot,
                         daily_revenue=daily_revenue,
                         top_users=top_users,
                         all_lots=all_lots,
                         start_date=start_date,
                         end_date=end_date,
                         selected_lot_id=lot_id)

@admin.route('/reports/export')
@login_required
@admin_required
def export_reports():
    """Export revenue data as CSV."""
    import csv
    import io
    from flask import make_response
    
    # Get parameters
    start_date = request.args.get('start_date', datetime.now().replace(day=1).strftime('%Y-%m-%d'))
    end_date = request.args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
    lot_id = request.args.get('lot_id', type=int)
    
    start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
    end_datetime = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    # Query bookings
    query = db.session.query(
        Booking.id,
        Booking.created_at,
        Booking.start_time,
        Booking.end_time,
        Booking.total_amount,
        Booking.status,
        User.first_name,
        User.last_name,
        User.email,
        ParkingLot.name.label('lot_name'),
        ParkingSpot.spot_number
    ).join(User).join(ParkingSpot).join(ParkingLot).filter(
        and_(
            Booking.created_at >= start_datetime,
            Booking.created_at <= end_datetime,
            Booking.status.in_(['confirmed', 'completed'])
        )
    )
    
    if lot_id:
        query = query.filter(ParkingLot.id == lot_id)
    
    bookings = query.order_by(Booking.created_at.desc()).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'Booking ID', 'Created Date', 'Start Time', 'End Time', 'Amount',
        'Status', 'User Name', 'User Email', 'Parking Lot', 'Spot Number'
    ])
    
    # Write data
    for booking in bookings:
        writer.writerow([
            booking.id,
            booking.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            booking.start_time.strftime('%Y-%m-%d %H:%M:%S'),
            booking.end_time.strftime('%Y-%m-%d %H:%M:%S'),
            f'${booking.total_amount:.2f}',
            booking.status,
            f'{booking.first_name} {booking.last_name}',
            booking.email,
            booking.lot_name,
            booking.spot_number
        ])
    
    # Create response
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=revenue_report_{start_date}_to_{end_date}.csv'
    
    return response

# ===================== COMPLAINT MANAGEMENT =====================

@admin.route('/complaints')
@login_required
@admin_required
def complaints():
    """List all complaints with filtering and management options."""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '')
    priority_filter = request.args.get('priority', '')
    search = request.args.get('search', '')
    
    query = Complaint.query
    
    # Apply filters
    if status_filter:
        query = query.filter(Complaint.status == status_filter)
    
    if priority_filter:
        query = query.filter(Complaint.priority == priority_filter)
    
    if search:
        query = query.filter(
            or_(
                Complaint.subject.ilike(f'%{search}%'),
                Complaint.description.ilike(f'%{search}%')
            )
        )
    
    complaints = query.order_by(Complaint.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )
    
    # Get complaint statistics
    total_complaints = Complaint.query.count()
    pending_complaints = Complaint.query.filter_by(status='open').count()
    resolved_complaints = Complaint.query.filter_by(status='resolved').count()
    
    return render_template('admin/complaints.html',
                         complaints=complaints,
                         total_complaints=total_complaints,
                         pending_complaints=pending_complaints,
                         resolved_complaints=resolved_complaints,
                         status_filter=status_filter,
                         priority_filter=priority_filter,
                         search=search)

@admin.route('/complaints/<int:complaint_id>')
@login_required
@admin_required
def complaint_detail(complaint_id):
    """View detailed information about a complaint."""
    complaint = Complaint.query.get_or_404(complaint_id)
    return render_template('admin/complaint_detail.html', complaint=complaint)

@admin.route('/complaints/<int:complaint_id>/update-status', methods=['POST'])
@login_required
@admin_required
def update_complaint_status(complaint_id):
    """Update complaint status and add admin response."""
    complaint = Complaint.query.get_or_404(complaint_id)
    
    new_status = request.form.get('status')
    admin_response = request.form.get('admin_response', '').strip()
    
    if new_status in ['open', 'in_progress', 'resolved', 'closed']:
        complaint.status = new_status
        
        if admin_response:
            complaint.admin_response = admin_response
            complaint.resolved_at = datetime.now() if new_status == 'resolved' else None
        
        db.session.commit()
        flash(f'Complaint status updated to {new_status}.', 'success')
    else:
        flash('Invalid status provided.', 'danger')
    
    return redirect(url_for('admin.complaint_detail', complaint_id=complaint.id))

@admin.route('/complaints/<int:complaint_id>/assign-priority', methods=['POST'])
@login_required
@admin_required
def assign_complaint_priority(complaint_id):
    """Assign priority to a complaint."""
    complaint = Complaint.query.get_or_404(complaint_id)
    
    new_priority = request.form.get('priority')
    
    if new_priority in ['low', 'medium', 'high', 'urgent']:
        complaint.priority = new_priority
        db.session.commit()
        flash(f'Complaint priority set to {new_priority}.', 'success')
    else:
        flash('Invalid priority provided.', 'danger')
    
    return redirect(url_for('admin.complaint_detail', complaint_id=complaint.id))


# Admin Profile and Settings Routes
@admin.route('/profile')
@login_required
@admin_required
def profile():
    """Admin profile page."""
    # Get system statistics for admin overview
    total_users = User.query.count()
    total_lots = ParkingLot.query.count()
    total_bookings = Booking.query.count()
    total_revenue = db.session.query(func.sum(Booking.total_amount)).filter(
        Booking.status == 'confirmed'
    ).scalar() or 0
    
    # Get recent admin activity (recent users, lots, bookings)
    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_lots = ParkingLot.query.order_by(ParkingLot.created_at.desc()).limit(3).all()
    recent_bookings = Booking.query.order_by(Booking.created_at.desc()).limit(5).all()
    
    return render_template('admin/profile.html',
                         total_users=total_users,
                         total_lots=total_lots,
                         total_bookings=total_bookings,
                         total_revenue=total_revenue,
                         recent_users=recent_users,
                         recent_lots=recent_lots,
                         recent_bookings=recent_bookings)


@admin.route('/profile/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_profile():
    """Edit admin profile."""
    form = ProfileForm(obj=current_user)
    
    if form.validate_on_submit():
        # Check if email is being changed and if it's already taken
        if form.email.data != current_user.email:
            existing_user = User.query.filter_by(email=form.email.data).first()
            if existing_user:
                flash('Email address is already in use.', 'danger')
                return render_template('admin/edit_profile.html', form=form)
        
        try:
            current_user.first_name = form.first_name.data
            current_user.last_name = form.last_name.data
            current_user.email = form.email.data
            current_user.phone_number = form.phone_number.data
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('admin.profile'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating your profile.', 'danger')
    
    return render_template('admin/edit_profile.html', form=form)


@admin.route('/settings')
@login_required
@admin_required
def settings():
    """Admin settings page."""
    # Get system overview stats for settings page
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    total_managers = User.query.filter(User.managed_lots.any()).count()
    total_lots = ParkingLot.query.count()
    active_lots = ParkingLot.query.filter_by(is_active=True).count()
    
    return render_template('admin/settings.html',
                         total_users=total_users,
                         active_users=active_users,
                         total_managers=total_managers,
                         total_lots=total_lots,
                         active_lots=active_lots)


@admin.route('/settings/change-password', methods=['GET', 'POST'])
@login_required
@admin_required
def change_password():
    """Change admin password."""
    form = ChangePasswordForm()
    
    if form.validate_on_submit():
        # Verify current password
        if not current_user.check_password(form.current_password.data):
            flash('Current password is incorrect.', 'danger')
            return render_template('admin/change_password.html', form=form)
        
        try:
            current_user.set_password(form.new_password.data)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('admin.settings'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while changing your password.', 'danger')
    
    return render_template('admin/change_password.html', form=form)
