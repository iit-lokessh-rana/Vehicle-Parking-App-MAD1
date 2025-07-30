import click
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash
from app import db
from app.models.user import User
from app.models.parking import Address
from app.models.parking import ParkingLot
from app.models.parking import ParkingSpot
from app.models.parking import Booking
from app.models.parking import Transaction
from app.models.parking import Complaint

@click.command('init-db')
@with_appcontext
def init_db_command():
    """Initialize the database."""
    click.echo('Creating database tables...')
    db.create_all()
    click.echo('Database tables created.')

@click.command('create-admin')
@click.option('--email', prompt='Email', help='Admin email')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, 
              help='Admin password')
@click.option('--first-name', prompt='First name', help='Admin first name')
@click.option('--last-name', prompt='Last name', help='Admin last name')
@with_appcontext
def create_admin_user(email, password, first_name, last_name):
    """Create an admin user."""
    # Check if user already exists
    user = User.query.filter_by(email=email).first()
    if user:
        click.echo(f'User with email {email} already exists. Updating to admin...')
        user.is_admin = True
        user.first_name = first_name
        user.last_name = last_name
        user.set_password(password)
    else:
        # Create new admin user
        admin = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_admin=True,
            is_email_verified=True
        )
        admin.set_password(password)
        db.session.add(admin)
    
    db.session.commit()
    click.echo(f'Admin user {email} created/updated successfully.')

@click.command('seed-sample-data')
@with_appcontext
def seed_sample_data():
    """Seed the database with sample parking lots and spots."""
    click.echo('Seeding sample data...')
    if ParkingLot.query.count() > 0:
        click.echo('Sample data already exists. Skipping.')
        return

    # Create address
    from datetime import time
    addr = Address(street='123 Main St', city='Metropolis', state='NY', postal_code='10001', country='USA')
    db.session.add(addr)
    db.session.flush()

        # Create users if they don't already exist
    from werkzeug.security import generate_password_hash
    def get_or_create(email, **kwargs):
        user = User.query.filter_by(email=email).first()
        if user:
            return user
        user = User(email=email, **kwargs)
        db.session.add(user)
        return user

    super_admin = get_or_create('admin@example.com', first_name='Super', last_name='Admin', is_admin=True,
                                password_hash=generate_password_hash('admin123'))
    manager_user = get_or_create('manager@example.com', first_name='Lot', last_name='Manager', is_admin=False,
                                password_hash=generate_password_hash('manager123'))
    regular_user = get_or_create('user@example.com', first_name='Test', last_name='User', is_admin=False,
                                password_hash=generate_password_hash('user123'))
    db.session.flush()

    # Create lot with manager assigned
    lot = ParkingLot(name='Downtown Garage', address_id=addr.id, total_spots=30, available_spots=30, hourly_rate=5.0,
                     opening_time=time(6,0), closing_time=time(23,0), manager_id=manager_user.id)
    db.session.add(lot)
    db.session.flush()

    # Create spots
    for i in range(1, 31):
        spot_type = ParkingSpot.TYPE_REGULAR if i <= 20 else ParkingSpot.TYPE_ELECTRIC
        spot = ParkingSpot(
            spot_number=str(i),
            floor=1,
            spot_type=spot_type,
            is_available=True,
            has_charger=(spot_type == ParkingSpot.TYPE_ELECTRIC),
            parking_lot_id=lot.id
        )
        db.session.add(spot)

    db.session.commit()
    click.echo('Sample data inserted.')


def register_commands(app):
    """Register CLI commands with the application."""
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_user)
    app.cli.add_command(seed_sample_data)
