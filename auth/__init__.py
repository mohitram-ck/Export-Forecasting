from flask import Blueprint
from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()
auth_bp = Blueprint("auth", __name__)

from . import routes  # noqa: E402,F401
