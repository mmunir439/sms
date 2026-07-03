import os
import secrets
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from config import config

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()

# Security headers added to every response
SECURITY_HEADERS = {
    'X-Content-Type-Options':  'nosniff',
    'X-Frame-Options':         'SAMEORIGIN',
    'X-XSS-Protection':        '1; mode=block',
    'Referrer-Policy':         'strict-origin-when-cross-origin',
    'Permissions-Policy':      'geolocation=(), microphone=()',
    'Content-Security-Policy': (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "frame-ancestors 'self';"
    ),
}


def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)

    # ── CORS: only allow explicitly configured origins ──────────────────────
    allowed_origins = app.config.get('CORS_ORIGINS') or []
    if allowed_origins:
        CORS(app, origins=allowed_origins, supports_credentials=True)

    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.session_protection = 'strong'

    @login_manager.user_loader
    def load_user(user_id):
        from app.models.user import User
        return User.query.get(int(user_id))

    # ── Jinja2 Filters ──────────────────────────────────────────────────────────
    @app.template_filter('mask_last_7')
    def mask_last_7(value):
        """Mask last 7 digits of phone number with X"""
        if not value:
            return ''
        value = str(value)
        if len(value) >= 7:
            return value[:-7] + 'X' * 7
        return 'X' * len(value)

    @app.template_filter('mask_last_6')
    def mask_last_6(value):
        """Mask last 6 characters with X"""
        if not value:
            return ''
        value = str(value)
        if len(value) >= 6:
            return value[:-6] + 'X' * 6
        return 'X' * len(value)

    # ── Security headers on every response ──────────────────────────────────
    @app.after_request
    def add_security_headers(response):
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response

    # ── Error Handlers ─────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({'error': 'Page not found'}), 404

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        return jsonify({'error': 'An internal error occurred. Please try again later.'}), 500

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({'error': 'Access denied'}), 403

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({'error': 'Please log in to access this page'}), 401

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.api import api_bp
    from app.routes.admin import admin_bp
    from app.routes.sms_monitor import monitor_bp
    from app.routes.developer import dev_bp
    from app.routes.honeypot import honeypot_bp
    from app.routes.rings import rings_bp  # Rings System Blueprint

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(monitor_bp)
    app.register_blueprint(dev_bp)
    app.register_blueprint(honeypot_bp)
    app.register_blueprint(rings_bp)  # Register Rings Blueprint

    from app.routes.sms_monitor import start_background_worker
    start_background_worker(app)

    with app.app_context():
        db.create_all()

        # ── Create Rings tables (Rings System) ───────────────────────────────
        from sqlalchemy import text, inspect as sa_inspect
        inspector = sa_inspect(db.engine)
        tables = inspector.get_table_names()

        # ── Auto-migrate ────────────────────────────────────────────────────
        try:
            from sqlalchemy import text, inspect as sa_inspect
            inspector = sa_inspect(db.engine)
            tables = inspector.get_table_names()

            if 'sms_ranges' in tables:
                range_cols = [c['name'] for c in inspector.get_columns('sms_ranges')]
                if 'application' not in range_cols:
                    db.session.execute(text("ALTER TABLE sms_ranges ADD COLUMN application VARCHAR(50)"))
                    db.session.commit()

            if 'sms_cdr' in tables:
                cdr_cols = [c['name'] for c in inspector.get_columns('sms_cdr')]
                if 'caller_id' not in cdr_cols:
                    db.session.execute(text("ALTER TABLE sms_cdr ADD COLUMN caller_id VARCHAR(50)"))
                    db.session.commit()

            # ── Honeypot log table ──────────────────────────────────────────
            if 'honeypot_logs' not in tables:
                db.session.execute(text("""
                    CREATE TABLE honeypot_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ip TEXT NOT NULL,
                        path TEXT NOT NULL,
                        method TEXT NOT NULL,
                        user_agent TEXT,
                        body TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.session.commit()

            # ── Add title column to news table ──────────────────────────────
            if 'news' in tables:
                news_cols = [c['name'] for c in inspector.get_columns('news')]
                if 'title' not in news_cols:
                    db.session.execute(text("ALTER TABLE news ADD COLUMN title VARCHAR(200)"))
                    db.session.commit()

            # ── Add telegram columns to users table ─────────────────────────
            if 'users' in tables:
                user_cols = [c['name'] for c in inspector.get_columns('users')]
                if 'telegram_bot_token' not in user_cols:
                    db.session.execute(text("ALTER TABLE users ADD COLUMN telegram_bot_token VARCHAR(255)"))
                    db.session.execute(text("ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(100)"))
                    db.session.execute(text("ALTER TABLE users ADD COLUMN telegram_enabled BOOLEAN DEFAULT 0"))
                    db.session.commit()

            # ── Rings System Tables ──────────────────────────────────────────
            if 'rings' not in tables:
                db.session.execute(text("""
                    CREATE TABLE rings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(100) NOT NULL,
                        description TEXT,
                        price REAL NOT NULL DEFAULT 0.0,
                        currency VARCHAR(3) DEFAULT 'USD',
                        features TEXT,
                        is_active BOOLEAN DEFAULT 1,
                        sort_order INTEGER DEFAULT 0,
                        custom_link VARCHAR(255),
                        color VARCHAR(20) DEFAULT '#00d4ff',
                        icon VARCHAR(50) DEFAULT 'fa-circle',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.session.commit()

            if 'access_codes' not in tables:
                db.session.execute(text("""
                    CREATE TABLE access_codes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code VARCHAR(20) UNIQUE NOT NULL,
                        number INTEGER NOT NULL,
                        ring_id INTEGER REFERENCES rings(id),
                        price_paid REAL DEFAULT 0.0,
                        status VARCHAR(20) DEFAULT 'available',
                        used_at TIMESTAMP,
                        used_by VARCHAR(100),
                        buyer_contact VARCHAR(100),
                        notes TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.session.execute(text("CREATE INDEX ix_access_codes_code ON access_codes(code)"))
                db.session.commit()

            if 'ring_transactions' not in tables:
                db.session.execute(text("""
                    CREATE TABLE ring_transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code_id INTEGER REFERENCES access_codes(id),
                        ring_id INTEGER REFERENCES rings(id),
                        amount REAL NOT NULL,
                        currency VARCHAR(3) DEFAULT 'USD',
                        payment_method VARCHAR(50),
                        transaction_id VARCHAR(100),
                        status VARCHAR(20) DEFAULT 'pending',
                        buyer_info TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                db.session.commit()

            # ── Create default rings if none exist ──────────────────────────
            from app.models.ring import Ring
            if Ring.query.count() == 0:
                default_rings = [
                    Ring(name='الرينج الذهبي', description='أعلى جودة وأفضل مميزات', price=500, currency='USD',
                         color='#ffd700', icon='fa-star', is_active=True, sort_order=1),
                    Ring(name='الرينج الفضي', description='جودة عالية', price=300, currency='USD',
                         color='#c0c0c0', icon='fa-circle', is_active=True, sort_order=2),
                    Ring(name='الرينج البرونزي', description='بداية جيدة', price=150, currency='USD',
                         color='#cd7f32', icon='fa-circle', is_active=True, sort_order=3),
                ]
                for r in default_rings:
                    db.session.add(r)
                db.session.commit()

        except Exception:
            pass

        from app.models.user import User, Role
        from app.models.sms import SMDRange
        from app.models.developer import StaticAsset

        # ── Create Roles ───────────────────────────────────────────────────
        for role_name, display in [('admin', 'Administrator'), ('agent', 'Agent'),
                                    ('client', 'Client'), ('developer', 'Developer')]:
            if not Role.query.filter_by(name=role_name).first():
                db.session.add(Role(name=role_name, display_name=display))
        db.session.commit()

        admin_role = Role.query.filter_by(name='admin').first()
        client_role = Role.query.filter_by(name='client').first()

        # ── Admin account ────────────────────────────────────────────────────
        # Default password is "admin123" (can be changed via ADMIN_PASSWORD env var)
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
            admin = User(
                username='admin',
                email='admin@system.local',
                role=admin_role,
                is_active=True,
            )
            admin.set_password(admin_password)
            admin.generate_api_token()
            db.session.add(admin)
            db.session.commit()
            print("=" * 60)
            print("[SYSTEM] Admin account created.")
            print(f"  Username: admin")
            print(f"  Password: {admin_password}")
            print("=" * 60)

        # ── Test123 account (special account for OTP masking) ────────────────
        test123 = User.query.filter_by(username='test123').first()
        if not test123:
            test123 = User(
                username='test123',
                email='test123@system.local',
                role=client_role,
                is_active=True,
            )
            test123.set_password('test123')
            test123.generate_api_token()
            db.session.add(test123)
            db.session.commit()
            print("[SYSTEM] Test account created: test123 / test123")

        # ── Create default SMS ranges with price 0.007 ──────────────────────
        if SMDRange.query.count() == 0:
            sample_ranges = [
                SMDRange(name='United States', country='United States', operator='AT&T',
                         network_type='GSM', mcc='310', mnc='410',
                         currency='USD', rate=0.007, cost_per_sms=0.007,
                         memo='United States SMS', test_number='12025551234', is_active=True,
                         billing_cycle='monthly', manual_price=5.0),
                SMDRange(name='United Kingdom', country='United Kingdom', operator='Vodafone',
                         network_type='GSM', mcc='234', mnc='15',
                         currency='GBP', rate=0.007, cost_per_sms=0.007,
                         memo='UK SMS', test_number='447911123456', is_active=True,
                         billing_cycle='monthly', manual_price=4.0),
                SMDRange(name='Germany', country='Germany', operator='Deutsche Telekom',
                         network_type='GSM', mcc='262', mnc='1',
                         currency='EUR', rate=0.007, cost_per_sms=0.007,
                         memo='Germany SMS', test_number='4915112345678', is_active=True,
                         billing_cycle='monthly', manual_price=4.0),
            ]
            for r in sample_ranges:
                db.session.add(r)
            db.session.commit()

    return app
