"""
مسارات إدارة الرينج والأكواد - Rings Management Routes
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, make_response
from flask_login import login_required, current_user
from app import db
from app.models.ring import Ring, AccessCode, RingTransaction
from app.models.activity import ActivityLog
from datetime import datetime, timedelta
from functools import wraps
import random
import string

rings_bp = Blueprint('rings', __name__)


def admin_required(f):
    """ديكوريتر للتحقق من صلاحية الأدمن"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_admin():
            flash('Admin access required.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ======================== RINGS MANAGEMENT ========================

@rings_bp.route('/admin/rings')
@admin_required
def rings_list():
    """صفحة قائمة الرينج"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('search', '')

    query = Ring.query

    if search:
        query = query.filter(
            db.or_(
                Ring.name.like(f'%{search}%'),
                Ring.description.like(f'%{search}%')
            )
        )

    rings = query.order_by(Ring.sort_order.asc(), Ring.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # إحصائيات
    total_rings = Ring.query.count()
    active_rings = Ring.query.filter_by(is_active=True).count()
    total_codes = AccessCode.query.count()
    used_codes = AccessCode.query.filter_by(status='used').count()

    return render_template('admin/rings_list.html',
                           rings=rings,
                           stats={
                               'total_rings': total_rings,
                               'active_rings': active_rings,
                               'total_codes': total_codes,
                               'used_codes': used_codes
                           })


@rings_bp.route('/admin/rings/create', methods=['GET', 'POST'])
@admin_required
def create_ring():
    """إنشاء رينج جديد"""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        price = request.form.get('price', 0, type=float)
        currency = request.form.get('currency', 'USD')
        color = request.form.get('color', '#00d4ff')
        icon = request.form.get('icon', 'fa-circle')
        custom_link = request.form.get('custom_link')
        features = request.form.get('features')
        sort_order = request.form.get('sort_order', 0, type=int)

        if not name:
            flash('Ring name is required.', 'danger')
            return redirect(url_for('rings.create_ring'))

        ring = Ring(
            name=name,
            description=description,
            price=price,
            currency=currency,
            color=color,
            icon=icon,
            custom_link=custom_link,
            features=features,
            sort_order=sort_order,
            is_active=True
        )

        db.session.add(ring)
        db.session.commit()

        ActivityLog.log(
            current_user.id,
            'create_ring',
            f'Created ring: {name} with price {price} {currency}',
            ip_address=request.remote_addr
        )

        flash(f'Ring "{name}" created successfully!', 'success')
        return redirect(url_for('rings.rings_list'))

    return render_template('admin/ring_form.html', ring=None)


@rings_bp.route('/admin/rings/<int:ring_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_ring(ring_id):
    """تعديل رينج"""
    ring = Ring.query.get_or_404(ring_id)

    if request.method == 'POST':
        ring.name = request.form.get('name')
        ring.description = request.form.get('description')
        ring.price = request.form.get('price', 0, type=float)
        ring.currency = request.form.get('currency', 'USD')
        ring.color = request.form.get('color', '#00d4ff')
        ring.icon = request.form.get('icon', 'fa-circle')
        ring.custom_link = request.form.get('custom_link')
        ring.features = request.form.get('features')
        ring.sort_order = request.form.get('sort_order', 0, type=int)

        is_active = request.form.get('is_active')
        ring.is_active = bool(is_active)

        db.session.commit()

        ActivityLog.log(
            current_user.id,
            'edit_ring',
            f'Edited ring: {ring.name}',
            ip_address=request.remote_addr
        )

        flash(f'Ring "{ring.name}" updated successfully!', 'success')
        return redirect(url_for('rings.rings_list'))

    return render_template('admin/ring_form.html', ring=ring)


@rings_bp.route('/admin/rings/<int:ring_id>/delete', methods=['POST'])
@admin_required
def delete_ring(ring_id):
    """حذف رينج"""
    ring = Ring.query.get_or_404(ring_id)

    # حذف الأكواد المرتبطة
    AccessCode.query.filter_by(ring_id=ring_id).delete()

    ring_name = ring.name
    db.session.delete(ring)
    db.session.commit()

    ActivityLog.log(
        current_user.id,
        'delete_ring',
        f'Deleted ring: {ring_name}',
        ip_address=request.remote_addr
    )

    flash(f'Ring "{ring_name}" and all its codes deleted.', 'success')
    return redirect(url_for('rings.rings_list'))


@rings_bp.route('/admin/rings/<int:ring_id>/toggle', methods=['POST'])
@admin_required
def toggle_ring(ring_id):
    """تبديل حالة الرينج"""
    ring = Ring.query.get_or_404(ring_id)
    ring.is_active = not ring.is_active
    db.session.commit()

    status = 'activated' if ring.is_active else 'deactivated'
    flash(f'Ring "{ring.name}" {status}.', 'success')

    return redirect(url_for('rings.rings_list'))


# ======================== CODES MANAGEMENT ========================

@rings_bp.route('/admin/codes')
@admin_required
def codes_list():
    """صفحة قائمة الأكواد"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    search = request.args.get('search', '')
    ring_filter = request.args.get('ring', '')
    status_filter = request.args.get('status', '')

    query = AccessCode.query

    if search:
        query = query.filter(
            db.or_(
                AccessCode.code.like(f'%{search}%'),
                AccessCode.number == int(search) if search.isdigit() else False
            )
        )

    if ring_filter:
        query = query.filter_by(ring_id=int(ring_filter))

    if status_filter:
        query = query.filter_by(status=status_filter)

    codes = query.order_by(AccessCode.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    rings = Ring.query.filter_by(is_active=True).order_by(Ring.sort_order.asc()).all()

    return render_template('admin/codes_list.html',
                           codes=codes,
                           rings=rings,
                           filters={'ring': ring_filter, 'status': status_filter})


@rings_bp.route('/admin/codes/create', methods=['GET', 'POST'])
@admin_required
def create_codes():
    """إنشاء أكواد جديدة"""
    rings = Ring.query.filter_by(is_active=True).order_by(Ring.sort_order.asc()).all()

    if request.method == 'POST':
        ring_id = request.form.get('ring_id', type=int)
        count = request.form.get('count', 1, type=int)

        if not ring_id:
            flash('Please select a ring.', 'danger')
            return redirect(url_for('rings.create_codes'))

        ring = Ring.query.get_or_404(ring_id)
        created_codes = []

        for _ in range(count):
            code_str = AccessCode.generate_code(8)
            number = AccessCode.generate_number(1000, 9999)

            # التأكد من عدم تكرار الكود أو الرقم
            while AccessCode.query.filter_by(code=code_str).first() or \
                  AccessCode.query.filter_by(number=number, ring_id=ring_id).first():
                code_str = AccessCode.generate_code(8)
                number = AccessCode.generate_number(1000, 9999)

            access_code = AccessCode(
                code=code_str,
                number=number,
                ring_id=ring_id,
                price_paid=ring.price,
                status='available'
            )
            db.session.add(access_code)
            created_codes.append(access_code)

        db.session.commit()

        ActivityLog.log(
            current_user.id,
            'create_codes',
            f'Created {count} codes for ring: {ring.name}',
            ip_address=request.remote_addr
        )

        flash(f'{count} codes created for "{ring.name}"!', 'success')
        return redirect(url_for('rings.codes_list'))

    return render_template('admin/codes_create.html', rings=rings)


@rings_bp.route('/admin/codes/<int:code_id>/delete', methods=['POST'])
@admin_required
def delete_code(code_id):
    """حذف كود"""
    code = AccessCode.query.get_or_404(code_id)
    code_str = code.code
    db.session.delete(code)
    db.session.commit()

    ActivityLog.log(
        current_user.id,
        'delete_code',
        f'Deleted code: {code_str}',
        ip_address=request.remote_addr
    )

    flash(f'Code "{code_str}" deleted.', 'success')
    return redirect(url_for('rings.codes_list'))


@rings_bp.route('/admin/codes/export')
@admin_required
def export_codes():
    """تصدير الأكواد كملف CSV"""
    ring_id = request.args.get('ring_id', type=int)
    status = request.args.get('status', '')

    query = AccessCode.query

    if ring_id:
        query = query.filter_by(ring_id=ring_id)
    if status:
        query = query.filter_by(status=status)

    codes = query.all()

    # إنشاء محتوى CSV
    csv_content = "Code,Number,Ring,Price,Status,Created At\n"
    for code in codes:
        csv_content += f'{code.code},{code.number},"{code.ring.name if code.ring else ""}",{code.price_paid},{code.status},{code.created_at.strftime("%Y-%m-%d %H:%M:%S")}\n'

    response = make_response(csv_content)
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=rings_codes_{datetime.utcnow().strftime("%Y%m%d_%H%M%S")}.csv'

    return response


# ======================== VERIFICATION (Public) ========================

@rings_bp.route('/verify')
def verify_code():
    """صفحة التحقق من الكود (للعميل)"""
    code = request.args.get('code', '').strip()
    number = request.args.get('number', '').strip()

    if code and number:
        access_code = AccessCode.query.filter_by(
            code=code.upper(),
            number=int(number)
        ).first()

        if access_code:
            if access_code.status == 'used':
                return render_template('verify.html',
                                       error='هذا الكود تم استخدامه بالفعل')

            # جلب الرينج والمعلومات
            ring = access_code.ring

            if not ring or not ring.is_active:
                return render_template('verify.html',
                                       error='الرينج غير متاح حالياً')

            return render_template('verify.html',
                                   success=True,
                                   code=access_code.code,
                                   number=access_code.number,
                                   ring_name=ring.name,
                                   ring_price=ring.price,
                                   custom_link=ring.custom_link)

        return render_template('verify.html',
                               error='الكود أو الرقم غير صحيح')

    return render_template('verify.html')


@rings_bp.route('/api/verify', methods=['POST'])
def api_verify():
    """API للتحقق من الكود"""
    data = request.json
    code = data.get('code', '').strip()
    number = data.get('number', '').strip()

    if not code or not number:
        return jsonify({'error': 'Code and number are required'}), 400

    access_code = AccessCode.query.filter_by(
        code=code.upper(),
        number=int(number)
    ).first()

    if not access_code:
        return jsonify({'error': 'Invalid code or number'}), 404

    if access_code.status == 'used':
        return jsonify({'error': 'This code has already been used'}), 400

    ring = access_code.ring

    if not ring or not ring.is_active:
        return jsonify({'error': 'Ring is not available'}), 400

    return jsonify({
        'success': True,
        'code': access_code.code,
        'number': access_code.number,
        'ring_name': ring.name,
        'ring_price': ring.price,
        'custom_link': ring.custom_link
    })


@rings_bp.route('/api/activate', methods=['POST'])
def api_activate():
    """API لتفعيل الكود (بعد الدفع)"""
    data = request.json
    code = data.get('code', '').strip()
    number = data.get('number', '').strip()
    buyer_info = data.get('buyer_info', '')

    access_code = AccessCode.query.filter_by(
        code=code.upper(),
        number=int(number)
    ).first()

    if not access_code:
        return jsonify({'error': 'Invalid code or number'}), 404

    if access_code.status == 'used':
        return jsonify({'error': 'This code has already been used'}), 400

    access_code.status = 'used'
    access_code.used_at = datetime.utcnow()
    access_code.used_by = request.remote_addr
    access_code.buyer_contact = buyer_info

    db.session.commit()

    return jsonify({
        'success': True,
        'message': 'Code activated successfully',
        'redirect_url': access_code.ring.custom_link if access_code.ring and access_code.ring.custom_link else '/'
    })


# ======================== DASHBOARD WIDGET ========================

@rings_bp.route('/admin/rings/stats')
@admin_required
def rings_stats():
    """إحصائيات الرينج للأدمن"""
    rings = Ring.query.filter_by(is_active=True).all()

    stats = {
        'total_rings': Ring.query.count(),
        'active_rings': Ring.query.filter_by(is_active=True).count(),
        'total_codes': AccessCode.query.count(),
        'available_codes': AccessCode.query.filter_by(status='available').count(),
        'used_codes': AccessCode.query.filter_by(status='used').count(),
        'total_revenue': db.session.query(db.func.sum(AccessCode.price_paid)).filter(
            AccessCode.status == 'used'
        ).scalar() or 0
    }

    rings_data = [{
        'id': r.id,
        'name': r.name,
        'price': r.price,
        'codes_count': r.get_codes_count(),
        'used_codes': r.get_used_codes_count(),
        'revenue': r.get_total_revenue()
    } for r in rings]

    return jsonify({
        'stats': stats,
        'rings': rings_data
    })
