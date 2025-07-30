# Parking System Web App

A full-stack Flask application that lets users book parking spots, make payments (Stripe), and manage lots with admin & manager roles.

## Features

- User registration & authentication
- Role-based dashboards (User, Manager, Admin)
- Parking spot booking, approval, rejection, and cancellation
- Stripe payment integration with receipts & history
- Responsive Bootstrap 5 UI
- Database: SQLite

---

## 🏃‍♂️ Quick Start

1. **Clone the repo**

   unzip the downloaded zip file
   open terminal / command prompt and navigate to the unzipped folder

2. **Create & activate a virtual environment** (recommended)

   python -m venv venv
   
   # On Mac / Linux based systems:
   source venv/bin/activate  
   
   # On Windows:
   venv\Scripts\activate


3. **Install dependencies**

   pip install -r requirements.txt

4. **Configure environment variables**

   Create a `.env` file (or export vars in your shell) with at least:

   SECRET_KEY=change-me
   # Stripe keys (required for real payments)
   STRIPE_PUBLISHABLE_KEY=pk_test_...
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...   # optional unless you enable webhooks

5. **Set Flask environment**

   export FLASK_APP=app:create_app   # Windows PowerShell: $env:FLASK_APP="app:create_app"
   export FLASK_ENV=development      # enables debug reload

6. **Initialize the database**

   flask db upgrade   # applies migrations (creates app.db)

   The first run seeds a default admin account:

   * **Email:** `admin@example.com`
   * **Password:** `admin123`

7. **Run the dev server**

   flask run

   Open `http://127.0.0.1:5000` in your browser.

---

## 🛠  Useful Commands

| Command | Description |
|---------|-------------|
| `flask shell` | Opens a REPL with app context & DB imported |
| `flask db migrate -m "msg"` | Generate migration scripts |
| `flask db upgrade` | Apply migrations |
| `flask db downgrade` | Roll back migrations |

---

## Deployment

The app is self-contained and can run on any WSGI server (Gunicorn, uWSGI). Point the server to `app:create_app()`.

```bash
gunicorn 'app:create_app()'
```

For production, **set real Stripe keys** 

