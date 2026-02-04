from flask import Blueprint, render_template, request, jsonify, send_file
from flask_login import login_required, current_user
from flask_login import logout_user
from flask import  redirect, url_for, flash
from extensions import db
from models import User, Student, Class, Batch, CIEPapers# Ensure these match your model names
from sqlalchemy import text
import json
import os

hod_bp = Blueprint('hod', __name__, url_prefix='/hod')

# ================= HELPER =================
def is_hod():
    # Check if user is logged in AND has the role name 'hod'
    return current_user.is_authenticated and \
           hasattr(current_user, 'role') and \
           current_user.role.role_name.lower() == 'hod'

@hod_bp.route('/cie-uploads')
@login_required
def get_cie_uploads():
    return jsonify([]) # Return empty list for now


@hod_bp.route("/dashboard")
@login_required
def dashboard(): # <--- This function name must be 'dashboard'
    return render_template("hod.html") # Ensure your HTML file name is correct


auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for('auth.login'))







# ================= DASHBOARD STATS =================
@hod_bp.route('/dashboard-stats')
@login_required
def get_stats():
    if not is_hod(): return jsonify({'error': 'Unauthorized'}), 403
    
    branch_id = current_user.branch_id
    
    # 1. Count students belonging ONLY to this HOD's branch
    student_count = db.session.query(Student).filter_by(branch_id=branch_id).count()
    
    # 2. FIX: Count ONLY users belonging to this HOD's branch 
    # Optional: Filter by role_id to count only 'staff' lecturers
    staff_count = db.session.query(User).filter_by(branch_id=branch_id).count() 
    
    # If you want to be precise and count ONLY staff (not other HODs in same branch if any):
    # staff_count = db.session.query(User).join(User.role).filter(
    #     User.branch_id == branch_id, 
    #     text("roles.role_name = 'staff'")
    # ).count()
    
    # Get current control statuses
    controls = db.session.execute(text(
        "SELECT setting_key, setting_value FROM department_controls WHERE branch_id = :bid"
    ), {'bid': branch_id}).fetchall()
    
    # Convert list of tuples to a dictionary
    control_data = {row[0]: (json.loads(row[1]) if isinstance(row[1], str) else row[1]) for row in controls}
    
    return jsonify({
        "hod_name": current_user.username,
        "student_count": student_count,
        "staff_count": staff_count,
        "attendance_status": control_data.get('attendance_enabled', {"enabled": False}),
        "cie_status": control_data.get('cie_enabled', {"enabled": False})
    })

# ================= STUDENT MANAGEMENT =================
@hod_bp.route('/students')
@login_required
def list_students():
    # Join with classes to get semester name
    query = text("""
        SELECT s.register_no, s.name, c.class_name, b.batch_name 
        FROM students s
        JOIN classes c ON s.class_id = c.class_id
        LEFT JOIN batches b ON s.batch_id = b.batch_id
        WHERE s.branch_id = :bid
    """)
    result = db.session.execute(query, {'bid': current_user.branch_id}).fetchall()
    return jsonify([dict(zip(['register_no', 'name', 'semester', 'batch'], row)) for row in result])

@hod_bp.route('/add-student', methods=['POST'])
@login_required
def add_student():
    data = request.json
    # Finding class_id based on UI selection
    target_class = Class.query.filter_by(branch_id=current_user.branch_id, class_name=f"Semester {data['semester']}").first()
    
    new_student = Student(
        register_no=data['register_no'],
        name=data['name'],
        branch_id=current_user.branch_id,
        class_id=target_class.class_id if target_class else None,
        is_active=1
    )
    db.session.add(new_student)
    db.session.commit()
    return jsonify({"status": "success"})

# ================= STAFF ALLOCATION =================
@hod_bp.route('/allocations')
@login_required
def get_allocations():
    query = text("""
        SELECT c.class_name, sa.subject_name, u.username, b.batch_name, sa.allocation_id
        FROM staff_allocations sa
        JOIN users u ON sa.staff_id = u.user_id
        JOIN classes c ON sa.class_id = c.class_id
        LEFT JOIN batches b ON sa.batch_id = b.batch_id
        WHERE c.branch_id = :bid
    """)
    result = db.session.execute(query, {'bid': current_user.branch_id}).fetchall()
    return jsonify([dict(zip(['semester', 'subject', 'staff', 'batch', 'id'], row)) for row in result])

@hod_bp.route('/create-allocation', methods=['POST'])
@login_required
def create_allocation():
    data = request.json
    # Logic to handle Theory (batch_id=NULL) or Lab (resolve batch_id)
    target_class = Class.query.filter_by(branch_id=current_user.branch_id, class_name=f"Semester {data['sem']}").first()
    
    batch_id = None
    if 'lab' in data['type'].lower():
        batch_name = 'A' if 'a' in data['type'].lower() else 'B'
        batch = Batch.query.filter_by(class_id=target_class.class_id, batch_name=batch_name).first()
        batch_id = batch.batch_id if batch else None

    sql = text("""
        INSERT INTO staff_allocations (staff_id, class_id, batch_id, subject_name)
        VALUES (:sid, :cid, :bid, :sname)
    """)
    db.session.execute(sql, {
        'sid': data['staff'], 'cid': target_class.class_id, 
        'bid': batch_id, 'sname': data['subject']
    })
    db.session.commit()
    return jsonify({"status": "success"})

# ================= CONTROLLERS =================
@hod_bp.route('/update-control', methods=['POST'])
@login_required
def update_control():
    data = request.json
    key = 'attendance_enabled' if data['type'] == 'attendance' else 'cie_enabled'
    
    # UPSERT logic for department_controls
    check = db.session.execute(text(
        "SELECT control_id FROM department_controls WHERE branch_id = :bid AND setting_key = :key"
    ), {'bid': current_user.branch_id, 'key': key}).fetchone()
    
    val = json.dumps({"enabled": data['enabled'], "details": data.get('details', {})})
    
    if check:
        db.session.execute(text(
            "UPDATE department_controls SET setting_value = :val WHERE control_id = :id"
        ), {'val': val, 'id': check[0]})
    else:
        db.session.execute(text(
            "INSERT INTO department_controls (branch_id, setting_key, setting_value) VALUES (:bid, :key, :val)"
        ), {'bid': current_user.branch_id, 'key': key, 'val': val})
        
    db.session.commit()
    return jsonify({"status": "success"})