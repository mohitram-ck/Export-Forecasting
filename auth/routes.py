import re

from flask import render_template, request, redirect, url_for, flash, session

from . import auth_bp, bcrypt
from database.models import insert_user, get_user_by_email


def _validate_email(email: str) -> bool:
    pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
    return re.match(pattern, email) is not None


def _validate_username(username: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9]{3,20}$", username))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_user_by_email(email)
        if not user or not bcrypt.check_password_hash(user["password"], password):
            flash("Invalid email or password", "error")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session.permanent = True
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not _validate_username(username):
            flash(
                "Username must be 3-20 characters and alphanumeric only.",
                "error",
            )
            return render_template("register.html")

        if not _validate_email(email):
            flash("Please enter a valid email address.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template("register.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

        success = insert_user(username=username, email=email, password_hash=password_hash)
        if not success:
            flash("Username or email already exists. Please try another.", "error")
            return render_template("register.html")

        flash("Account created! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))

