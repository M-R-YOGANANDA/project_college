from flask import Blueprint, render_template

staff_bp = Blueprint("staff", __name__)

@staff_bp.route("/")
def staff_dashboard():
    return render_template("login.html")
