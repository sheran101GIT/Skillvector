from flask import Flask
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_executor import Executor
from .config import Config
from .db import db
from .models import User

migrate = Migrate()
login_manager = LoginManager()
executor = Executor()
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    executor.init_app(app)
    
    from flask_wtf.csrf import CSRFProtect
    csrf = CSRFProtect(app)

    from .auth import auth as auth_blueprint
    app.register_blueprint(auth_blueprint)

    from .routes.main import bp as main_bp
    app.register_blueprint(main_bp)

    from .routes.jobs import bp as jobs_bp
    app.register_blueprint(jobs_bp)

    from .routes import candidates
    app.register_blueprint(candidates.bp)
    
    from .routes import reviews
    app.register_blueprint(reviews.bp)

    from .routes import analysis
    app.register_blueprint(analysis.bp)

    from .routes import uploads
    app.register_blueprint(uploads.bp)
    
    from .routes.api import bp as api_bp
    app.register_blueprint(api_bp)
    
    # Exempt API from CSRF (for Webhooks)
    csrf.exempt(api_bp)

    return app
