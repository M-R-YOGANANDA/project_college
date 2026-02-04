from flask import Blueprint, request, render_template, redirect, url_for, session
from flask_login import login_user, logout_user
from services.auth_service import authenticate_user

# --- NEW IMPORT: For Maintenance Check ---
from models.maintain import MaintenanceMode 

# Define the blueprint
auth_bp = Blueprint("auth", __name__)

# =========================================================
# LOGIN ROUTE
# =========================================================
@auth_bp.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # 1. Basic Validation
        if not username or not password:
            return render_template(
                "login.html",
                error="Username and password are required"
            )

        # 2. Authenticate User
        user = authenticate_user(username, password)

        if not user:
            return render_template(
                "login.html",
                error="Invalid username or password"
            )

        # --- MERGED: MAINTENANCE MODE CHECK START ---
        # Fetch the maintenance status (ID 1)
        maintenance = MaintenanceMode.query.get(1)
        
        # If Maintenance is ON (True) and User is NOT Admin (Role ID 1)
        if maintenance and maintenance.is_maintenance:
            if user.role_id != 1:
                return render_template(
                    "login.html", 
                    error="⚠️ System is under maintenance. Please try again later."
                )
        # --- MERGED: MAINTENANCE MODE CHECK END ---

        # 3. Log the user in with Flask-Login (Crucial Step)
        login_user(user)

        # 4. Set Session Variables (Optional, but good for your legacy logic)
        session["user_id"] = user.user_id
        session["role_id"] = user.role_id

        # 5. Role-Based Redirect
        if user.role_id == 1:
            return redirect(url_for("admin.admin_dashboard"))
        elif user.role_id == 2:
            return redirect(url_for("hod.dashboard"))
        elif user.role_id == 3:
            return redirect(url_for("staff.dashboard"))
        else:
            return render_template("login.html", error="Unauthorized role")

    return render_template("login.html")

# =========================================================
# LOGOUT ROUTE
# =========================================================
@auth_bp.route("/logout")
def logout():
    logout_user()      # Tell Flask-Login to wipe the user session
    session.clear()    # Wipe any manual session data you stored
    return redirect(url_for("auth.login"))