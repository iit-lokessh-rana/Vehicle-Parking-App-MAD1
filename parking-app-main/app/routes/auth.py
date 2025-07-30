from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from app.models.user import User
from app import db
from app.forms import LoginForm, RegistrationForm

# Auth blueprint
auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        
        # Check if user exists and password is correct
        if not user or not user.check_password(form.password.data):
            flash('Please check your login details and try again.', 'danger')
            return redirect(url_for('auth.login'))
            
        # Check if user is active
        if not user.is_active:
            flash('Your account is inactive. Please contact support.', 'warning')
            return redirect(url_for('auth.login'))
            
        # Log the user in
        login_user(user, remember=form.remember.data)
        
        # Redirect to next page if it exists, otherwise redirect to appropriate dashboard
        next_page = request.args.get('next')
        if not next_page:
            # Redirect to appropriate dashboard based on user role
            if user.is_admin:
                next_page = url_for('admin.dashboard')
            elif user.managed_lots:
                next_page = url_for('manager.dashboard')
            else:
                next_page = url_for('user.dashboard')
        
        flash('You have been logged in!', 'success')
        return redirect(next_page)
    
    return render_template('auth/login.html', form=form)

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
        
    form = RegistrationForm()
    if form.validate_on_submit():
        # Create new user
        user = User(
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            email=form.email.data,
            phone_number=form.phone_number.data,
            is_admin=False,  # Regular users are not admins
            is_active=True   # New users are active by default
        )
        user.set_password(form.password.data)
        
        try:
            db.session.add(user)
            db.session.commit()
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.', 'danger')
            
    return render_template('auth/register.html', form=form)


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.index'))