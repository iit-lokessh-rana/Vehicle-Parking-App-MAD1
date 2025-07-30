from datetime import datetime

from app import db

class RefundRequest(db.Model):
    """Represents a requested refund that awaits manager/admin approval."""

    __tablename__ = 'refund_requests'

    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_DENIED = 'denied'

    id = db.Column(db.Integer, primary_key=True)

    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'), nullable=False)
    payment = db.relationship('Payment', backref=db.backref('refund_requests', lazy='dynamic'))

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    requester = db.relationship('User', backref='refund_requests')

    requested_amount = db.Column(db.Numeric(10, 2), nullable=False)
    reason = db.Column(db.String(255))

    status = db.Column(db.String(20), default=STATUS_PENDING)
    approver_id = db.Column(db.Integer, db.ForeignKey('users.id'))  # admin/manager who processed
    approver = db.relationship('User', foreign_keys=[approver_id])

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)

    def mark_approved(self, approver_id):
        self.status = self.STATUS_APPROVED
        self.approver_id = approver_id
        self.resolved_at = datetime.utcnow()

    def mark_denied(self, approver_id):
        self.status = self.STATUS_DENIED
        self.approver_id = approver_id
        self.resolved_at = datetime.utcnow()

    def __repr__(self):
        return f'<RefundRequest {self.id} {self.status} ${self.requested_amount}>'
