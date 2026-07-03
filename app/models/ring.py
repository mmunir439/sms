"""
نظام الرينج - Rings System
كل رينج له سعر مختلف وكل كود دخول يأتي مع رقم
"""

from app import db
from datetime import datetime
import random
import string


class Ring(db.Model):
    """نموذج الرينج - يمثل مستوى/فئة مختلفة بسعر مخصص"""
    __tablename__ = 'rings'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False, default=0.0)  # السعر المخصص لهذا الرينج
    currency = db.Column(db.String(3), default='USD')

    # مميزات الرينج
    features = db.Column(db.Text)  # JSON string للمميزات

    # الإعدادات
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)  # لترتيب العرض

    # الرابط المرتبط بالرينج (إذا كان لكل رينج رابط مخصص)
    custom_link = db.Column(db.String(255))

    # الألوان والتصميم
    color = db.Column(db.String(20), default='#00d4ff')  # لون الرينج للعرض
    icon = db.Column(db.String(50), default='fa-circle')  # أيقونة الرينج

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # العلاقات
    codes = db.relationship('AccessCode', backref='ring', lazy='dynamic')

    def __repr__(self):
        return f'<Ring {self.name} - {self.price}>'

    def get_codes_count(self):
        """عدد الأكواد لهذا الرينج"""
        return self.codes.count()

    def get_used_codes_count(self):
        """عدد الأكواد المستخدمة"""
        return self.codes.filter_by(status='used').count()

    def get_available_codes_count(self):
        """عدد الأكواد المتاحة"""
        return self.codes.filter_by(status='available').count()

    def get_total_revenue(self):
        """إجمالي الإيرادات من هذا الرينج"""
        from sqlalchemy import func
        result = db.session.query(func.sum(AccessCode.price_paid)).filter(
            AccessCode.ring_id == self.id,
            AccessCode.status == 'used'
        ).scalar()
        return result or 0

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'price': self.price,
            'currency': self.currency,
            'features': self.features,
            'is_active': self.is_active,
            'sort_order': self.sort_order,
            'custom_link': self.custom_link,
            'color': self.color,
            'icon': self.icon,
            'codes_count': self.get_codes_count(),
            'used_codes': self.get_used_codes_count(),
            'available_codes': self.get_available_codes_count(),
            'total_revenue': self.get_total_revenue(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class AccessCode(db.Model):
    """نموذج كود الدخول - كل كود يأتي مع رقم"""
    __tablename__ = 'access_codes'

    id = db.Column(db.Integer, primary_key=True)

    # الكود نفسه (8 أحرف/أرقام)
    code = db.Column(db.String(20), unique=True, nullable=False, index=True)

    # الرقم المرتبط بالكود (4 أرقام)
    number = db.Column(db.Integer, nullable=False)

    # الرينج المرتبط
    ring_id = db.Column(db.Integer, db.ForeignKey('rings.id'), nullable=False)

    # السعر المدفوع عند الشراء
    price_paid = db.Column(db.Float, default=0.0)

    # حالة الكود
    status = db.Column(db.String(20), default='available')  # available, used, expired

    # معلومات الاستخدام
    used_at = db.Column(db.DateTime)
    used_by = db.Column(db.String(100))  # IP أو معرف المستخدم

    # رقم الهاتف أو البريد الإلكتروني للمشتري
    buyer_contact = db.Column(db.String(100))

    # ملاحظات
    notes = db.Column(db.Text)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<AccessCode {self.code} - {self.number}>'

    @staticmethod
    def generate_code(length=8):
        """توليد كود عشوائي"""
        chars = string.ascii_uppercase + string.digits
        return ''.join(random.choices(chars, k=length))

    @staticmethod
    def generate_number(min_val=1000, max_val=9999):
        """توليد رقم عشوائي (4 أرقام)"""
        return random.randint(min_val, max_val)

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'number': self.number,
            'ring_id': self.ring_id,
            'ring_name': self.ring.name if self.ring else None,
            'ring_price': self.ring.price if self.ring else 0,
            'price_paid': self.price_paid,
            'status': self.status,
            'used_at': self.used_at.isoformat() if self.used_at else None,
            'used_by': self.used_by,
            'buyer_contact': self.buyer_contact,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class RingTransaction(db.Model):
    """نموذج المعاملات - لتتبع المدفوعات"""
    __tablename__ = 'ring_transactions'

    id = db.Column(db.Integer, primary_key=True)

    code_id = db.Column(db.Integer, db.ForeignKey('access_codes.id'))
    ring_id = db.Column(db.Integer, db.ForeignKey('rings.id'))

    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD')

    payment_method = db.Column(db.String(50))  # visa, wallet, etc.
    transaction_id = db.Column(db.String(100))  # معرف العملية من بوابة الدفع

    status = db.Column(db.String(20), default='pending')  # pending, completed, failed, refunded

    buyer_info = db.Column(db.Text)  # JSON string للمعلومات الإضافية

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'code_id': self.code_id,
            'ring_id': self.ring_id,
            'ring_name': self.ring.name if self.ring else None,
            'amount': self.amount,
            'currency': self.currency,
            'payment_method': self.payment_method,
            'transaction_id': self.transaction_id,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
