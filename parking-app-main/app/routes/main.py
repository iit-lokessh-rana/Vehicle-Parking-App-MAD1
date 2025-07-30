from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

# Main blueprint
main = Blueprint('main', __name__)

@main.route('/')
def index():
    """Landing page."""
    if current_user.is_authenticated:
        # Redirect to appropriate dashboard based on user role
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        elif current_user.managed_lots:  # User is a manager
            return redirect(url_for('manager.dashboard'))
        else:
            return redirect(url_for('user.dashboard'))
    return render_template('main/index.html')

@main.route('/about')
def about():
    """About page."""
    return render_template('main/about.html')
