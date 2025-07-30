from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import stripe
import os
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models.parking import Booking, Payment, ParkingSpot
from app.forms import PaymentForm, BookingPaymentForm, RefundForm

payment_bp = Blueprint('payment', __name__, url_prefix='/payment')

# Configure Stripe - will be set in route functions to access current_app context

@payment_bp.route('/process/<int:booking_id>', methods=['GET', 'POST'])
@login_required
def process_payment(booking_id):
    """Process payment for a booking."""
    booking = Booking.query.get_or_404(booking_id)
    
    # Verify booking belongs to current user
    if booking.user_id != current_user.id:
        flash('Unauthorized access to booking.', 'error')
        return redirect(url_for('user.dashboard'))
    
    # Check if booking is already paid
    if booking.status == 'confirmed':
        flash('This booking has already been paid for.', 'info')
        return redirect(url_for('user.booking_list'))
    
    # Check if booking is expired
    if booking.start_time < datetime.utcnow():
        flash('This booking has expired and cannot be paid for.', 'error')
        return redirect(url_for('user.dashboard'))
    
    form = PaymentForm()
    
    if form.validate_on_submit():
        try:
            # Calculate amount
            amount = booking.calculate_amount()
            amount_cents = int(amount * 100)  # Stripe uses cents
            
            # Create payment record
            payment = Payment(
                booking_id=booking.id,
                user_id=current_user.id,
                amount=amount,
                payment_method=form.payment_method.data,
                status='pending'
            )
            
            # Process payment based on method
            if form.payment_method.data in ['credit_card', 'debit_card']:
                success, result = process_stripe_payment(
                    amount_cents=amount_cents,
                    card_number=form.card_number.data,
                    exp_month=int(form.expiry_month.data),
                    exp_year=int(form.expiry_year.data),
                    cvc=form.cvv.data,
                    billing_name=form.billing_name.data,
                    billing_email=form.billing_email.data or current_user.email
                )
                
                if success:
                    payment.status = 'completed'
                    payment.gateway_transaction_id = result.get('id')
                    payment.gateway_payment_intent_id = result.get('payment_intent')
                    payment.processed_at = datetime.utcnow()
                    
                    # Update booking status
                    booking.status = 'confirmed'
                    booking.total_amount = amount
                    
                    db.session.add(payment)
                    db.session.commit()
                    
                    flash('Payment successful! Your parking spot has been reserved.', 'success')
                    return redirect(url_for('payment.payment_success', payment_id=payment.id))
                else:
                    payment.status = 'failed'
                    payment.failure_reason = result.get('error', 'Payment processing failed')
                    db.session.add(payment)
                    db.session.commit()
                    
                    flash(f'Payment failed: {result.get("error", "Unknown error")}', 'error')
                    return redirect(url_for('payment.payment_failed', booking_id=booking.id, error=result.get('error')))
            
            elif form.payment_method.data == 'paypal':
                # PayPal integration would go here
                flash('PayPal integration coming soon!', 'info')
                return redirect(url_for('payment.process_payment', booking_id=booking_id))
            
            else:
                flash('Selected payment method is not yet supported.', 'error')
                return redirect(url_for('payment.process_payment', booking_id=booking_id))
                
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Payment processing error: {str(e)}')
            flash('An error occurred while processing your payment. Please try again.', 'error')
            return redirect(url_for('payment.payment_failed', booking_id=booking_id, error='Processing error'))
    
    return render_template('payment/payment_form.html', form=form, booking=booking)

@payment_bp.route('/success/<int:payment_id>')
@login_required
def payment_success(payment_id):
    """Display payment success page."""
    payment = Payment.query.get_or_404(payment_id)
    
    # Verify payment belongs to current user
    if payment.user_id != current_user.id:
        flash('Unauthorized access to payment.', 'error')
        return redirect(url_for('user.dashboard'))
    
    booking = payment.booking
    return render_template('payment/payment_success.html', payment=payment, booking=booking)

@payment_bp.route('/failed/<int:booking_id>')
@login_required
def payment_failed(booking_id):
    """Display payment failure page."""
    booking = Booking.query.get_or_404(booking_id)
    
    # Verify booking belongs to current user
    if booking.user_id != current_user.id:
        flash('Unauthorized access to booking.', 'error')
        return redirect(url_for('user.dashboard'))
    
    error_message = request.args.get('error', 'Payment processing failed')
    return render_template('payment/payment_failed.html', booking=booking, error_message=error_message)

@payment_bp.route('/refund-request/<int:payment_id>', methods=['GET', 'POST'])
@login_required
def request_refund(payment_id):
    """Allow user to submit a refund request (creates RefundRequest pending approval)."""
    payment = Payment.query.get_or_404(payment_id)

    # Ensure current user owns payment
    if payment.user_id != current_user.id:
        flash('Unauthorized access to payment.', 'error')
        return redirect(url_for('payment.payment_history'))

    # Only completed payments refundable
    if payment.status != 'completed':
        flash('Refunds can only be requested for completed payments.', 'error')
        return redirect(url_for('payment.payment_history'))

    # Cannot exceed remaining refundable amount
    remaining = float(payment.amount) - float(payment.refunded_amount or 0)
    if remaining <= 0:
        flash('This payment has already been fully refunded.', 'error')
        return redirect(url_for('payment.payment_history'))

    form = RefundRequestForm()
    if form.validate_on_submit():
        try:
            amount = float(form.refund_amount.data)
            if amount > remaining:
                flash(f'Refund amount cannot exceed ${remaining:.2f}', 'error')
                return render_template('payment/refund_request_form.html', form=form, payment=payment, remaining=remaining)

            refund_req = RefundRequest(
                payment_id=payment.id,
                user_id=current_user.id,
                requested_amount=amount,
                reason=form.refund_reason.data,
                status=RefundRequest.STATUS_PENDING
            )
            db.session.add(refund_req)
            db.session.commit()

            flash('Refund request submitted and is pending approval.', 'success')
            return redirect(url_for('payment.payment_history'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Refund request error: {str(e)}')
            flash('An error occurred while submitting request.', 'error')

    # Pre-fill with remaining
    if not form.refund_amount.data:
        form.refund_amount.data = f"{remaining:.2f}"

    return render_template('payment/refund_request_form.html', form=form, payment=payment, remaining=remaining)


@payment_bp.route('/refund/<int:payment_id>', methods=['GET', 'POST'])
@login_required
def process_refund(payment_id):
    """Process refund for a payment."""
    payment = Payment.query.get_or_404(payment_id)
    
    # Verify payment belongs to current user or user is admin
    if payment.user_id != current_user.id and not current_user.is_admin:
        flash('Unauthorized access to payment.', 'error')
        return redirect(url_for('user.dashboard'))
    
    # Check if refund is allowed
    if payment.status != 'completed':
        flash('Only completed payments can be refunded.', 'error')
        return redirect(url_for('user.booking_list'))
    
    if payment.refunded_amount and payment.refunded_amount >= payment.amount:
        flash('This payment has already been fully refunded.', 'error')
        return redirect(url_for('user.booking_list'))
    
    form = RefundForm()
    
    if form.validate_on_submit():
        try:
            refund_amount = float(form.refund_amount.data)
            
            # Validate refund amount
            max_refund = payment.amount - (payment.refunded_amount or 0)
            if refund_amount > max_refund:
                flash(f'Refund amount cannot exceed ${max_refund:.2f}', 'error')
                return render_template('payment/refund_form.html', form=form, payment=payment)
            
            # Process refund through Stripe
            if payment.gateway_payment_intent_id:
                success, result = process_stripe_refund(
                    payment_intent_id=payment.gateway_payment_intent_id,
                    amount_cents=int(refund_amount * 100),
                    reason=form.refund_reason.data
                )
                
                if success:
                    # Update payment record
                    payment.refunded_amount = (payment.refunded_amount or 0) + refund_amount
                    payment.refund_reference = result.get('id')
                    
                    # If fully refunded, update booking status
                    if payment.refunded_amount >= payment.amount:
                        payment.booking.status = 'cancelled'
                    
                    db.session.commit()
                    
                    flash(f'Refund of ${refund_amount:.2f} processed successfully.', 'success')
                    
                    # Send notification if requested
                    if form.notify_user.data:
                        # Email notification logic would go here
                        pass
                    
                    return redirect(url_for('user.booking_list'))
                else:
                    flash(f'Refund failed: {result.get("error", "Unknown error")}', 'error')
            else:
                flash('Cannot process refund: No payment intent found.', 'error')
                
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Refund processing error: {str(e)}')
            flash('An error occurred while processing the refund.', 'error')
    
    return render_template('payment/refund_form.html', form=form, payment=payment)

# --------------------
# Payment Receipt
# --------------------
@payment_bp.route('/receipt/<int:payment_id>')
@login_required
def payment_receipt(payment_id):
    """Display a printable receipt for a completed payment."""
    payment = Payment.query.get_or_404(payment_id)

    # Authorize: the payer, an admin, or a manager of the parking lot can view
    if payment.user_id != current_user.id and not getattr(current_user, 'is_admin', False) and not current_user.managed_lots:
        flash('You do not have permission to view this receipt.', 'error')
        return redirect(url_for('payment.payment_history'))

    booking = payment.booking  # convenient reference in template
    return render_template('payment/receipt.html', payment=payment, booking=booking)

@payment_bp.route('/history')
@login_required
def payment_history():
    """Display user's payment history."""
    page = request.args.get('page', 1, type=int)
    payments = Payment.query.filter_by(user_id=current_user.id)\
                           .order_by(Payment.created_at.desc())\
                           .paginate(page=page, per_page=10, error_out=False)
    
    return render_template('payment/payment_history.html', payments=payments)

@payment_bp.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Handle Stripe webhooks for payment status updates."""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')
    endpoint_secret = current_app.config.get('STRIPE_WEBHOOK_SECRET')
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
    except ValueError:
        current_app.logger.error('Invalid payload in Stripe webhook')
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError:
        current_app.logger.error('Invalid signature in Stripe webhook')
        return 'Invalid signature', 400
    
    # Handle the event
    if event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        # Update payment status in database
        payment = Payment.query.filter_by(gateway_payment_intent_id=payment_intent['id']).first()
        if payment:
            payment.status = 'completed'
            payment.processed_at = datetime.utcnow()
            db.session.commit()
    
    elif event['type'] == 'payment_intent.payment_failed':
        payment_intent = event['data']['object']
        # Update payment status in database
        payment = Payment.query.filter_by(gateway_payment_intent_id=payment_intent['id']).first()
        if payment:
            payment.status = 'failed'
            payment.failure_reason = payment_intent.get('last_payment_error', {}).get('message', 'Payment failed')
            db.session.commit()
    
    return 'Success', 200

def process_stripe_payment(amount_cents, card_number, exp_month, exp_year, cvc, billing_name, billing_email):
    """Process payment through Stripe."""
    # Set Stripe API key from config
    stripe_secret_key = current_app.config.get('STRIPE_SECRET_KEY')
    
    # Check if Stripe keys are configured for development/testing
    if not stripe_secret_key or stripe_secret_key.startswith('sk_test_') and stripe_secret_key == 'your_stripe_secret_key_here':
        # Dummy payment success for development/testing
        current_app.logger.info('Using dummy payment success - Stripe keys not configured')
        
        # Simulate some basic validation
        if not card_number or len(card_number.replace(' ', '')) < 13:
            return False, {'error': 'Invalid card number'}
        
        if not cvc or len(cvc) < 3:
            return False, {'error': 'Invalid CVV'}
            
        if not billing_name or len(billing_name.strip()) < 2:
            return False, {'error': 'Invalid billing name'}
        
        # Return dummy success response
        import uuid
        dummy_payment_id = f'dummy_pi_{uuid.uuid4().hex[:24]}'
        
        return True, {
            'id': dummy_payment_id,
            'payment_intent': dummy_payment_id,
            'dummy': True  # Flag to indicate this is a dummy payment
        }
    
    stripe.api_key = stripe_secret_key
    
    try:
        # Create payment method
        payment_method = stripe.PaymentMethod.create(
            type='card',
            card={
                'number': card_number.replace(' ', ''),
                'exp_month': exp_month,
                'exp_year': exp_year,
                'cvc': cvc,
            },
            billing_details={
                'name': billing_name,
                'email': billing_email,
            }
        )
        
        # Create payment intent
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            payment_method=payment_method.id,
            confirmation_method='manual',
            confirm=True,
            return_url=url_for('payment.payment_success', _external=True)
        )
        
        if payment_intent.status == 'succeeded':
            return True, {
                'id': payment_intent.id,
                'payment_intent': payment_intent.id
            }
        else:
            return False, {'error': 'Payment requires additional authentication'}
            
    except stripe.error.CardError as e:
        return False, {'error': e.user_message}
    except stripe.error.StripeError as e:
        return False, {'error': 'Payment processing error'}
    except Exception as e:
        current_app.logger.error(f'Stripe payment error: {str(e)}')
        return False, {'error': 'Payment processing failed'}

def process_stripe_refund(payment_intent_id, amount_cents, reason='requested_by_customer'):
    """Process refund through Stripe."""
    # Set Stripe API key from config
    stripe.api_key = current_app.config.get('STRIPE_SECRET_KEY')
    
    try:
        refund = stripe.Refund.create(
            payment_intent=payment_intent_id,
            amount=amount_cents,
            reason=reason
        )
        
        if refund.status == 'succeeded':
            return True, {'id': refund.id}
        else:
            return False, {'error': 'Refund processing failed'}
            
    except stripe.error.StripeError as e:
        return False, {'error': str(e)}
    except Exception as e:
        current_app.logger.error(f'Stripe refund error: {str(e)}')
        return False, {'error': 'Refund processing failed'}
