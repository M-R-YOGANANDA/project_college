from flask import (
    Blueprint, render_template, request, redirect, url_for, 
    session, jsonify, make_response,send_file,flash
)
from flask_login import current_user
from utils.decorators import role_required
from fpdf import FPDF
from models import User, Role, Setting, Student,Class
from models.branch import Branch
from models.maintain import MaintenanceMode
import os
from datetime import datetime
from sqlalchemy import inspect
# Try importing Class from 'models.classes'
# If your file is named differently (e.g., class_model.py), change 'classes' below.
from werkzeug.utils import secure_filename
import io
from extensions import db
from werkzeug.security import generate_password_hash
from datetime import datetime
import pandas as pd




admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
BACKUP_FOLDER = r"C:\Users\yogan\Desktop\projectbackup"
os.makedirs(BACKUP_FOLDER, exist_ok=True)


# ... (Keep dashboard and create-user routes exactly as they were) ...
@admin_bp.route("/dashboard")
@role_required("admin")
def admin_dashboard():
    return render_template(
        "admin.html",
        users=User.query.all(),
        hod_count=User.query.join(Role).filter(Role.role_name == "hod").count(),
        staff_count=User.query.join(Role).filter(Role.role_name == "staff").count(),
        students_count=Student.query.count(),
        branch_count=db.session.query(Student.branch_id).distinct().count()
    )
@admin_bp.route("/create-user", methods=["GET", "POST"])
@role_required("admin")
def create_user():
    if request.method == "POST":
        role_name = request.form["role"]
        branch_id_input = request.form.get("department")
        email_input = request.form["email"]
        
        # Fetch the selected role object
        role = Role.query.filter_by(role_name=role_name).first()
        
        # --- VALIDATION LOGIC FOR SINGLE HOD PER BRANCH ---
        if role_name.lower() == "hod":
            # Check if an HOD already exists for this branch_id
            existing_hod = User.query.filter_by(
                branch_id=branch_id_input, 
                role_id=role.role_id,
                is_active=True
            ).first()
            
            if existing_hod:
                error_msg = f"Error: An HOD for the requested department already exists ({existing_hod.username})."
                return render_template(
                    "create_user.html", 
                    roles=Role.query.all(), 
                    branches=Branch.query.all(), 
                    error=error_msg
                )
        # --------------------------------------------------

        try:
            user = User(
                username=email_input, 
                role_id=role.role_id,
                branch_id=branch_id_input, 
                password_hash=generate_password_hash(request.form["password"]),
                is_active=True
            )
            db.session.add(user)
            db.session.commit()
            return redirect(url_for("admin.admin_dashboard"))
        except Exception as e:
            db.session.rollback()
            return render_template(
                "create_user.html", 
                roles=Role.query.all(), 
                branches=Branch.query.all(), 
                error=str(e)
            )

    return render_template("create_user.html", roles=Role.query.all(), branches=Branch.query.all())
# =========================================================
# 1. SET MAINTENANCE (With debug prints)
# =========================================================
@admin_bp.route("/set-maintenance", methods=["POST"])
@role_required("admin")
def set_maintenance():
    try:
        data = request.get_json()
        enabled = bool(data.get("enabled", False))

        print(f"DEBUG: Toggling Maintenance to {enabled}") # Check your terminal for this

        mode = MaintenanceMode.query.get(1)
        if not mode:
            mode = MaintenanceMode(id=1, is_maintenance=enabled)
            db.session.add(mode)
        else:
            mode.is_maintenance = enabled

        db.session.commit()
        print("DEBUG: Database Committed Successfully")
        
        return jsonify({"status": "success", "enabled": enabled})
    except Exception as e:
        print(f"DEBUG ERROR: {e}")
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

# =========================================================
# 2. GET MAINTENANCE (With Cache Busting)
# =========================================================
@admin_bp.route("/get-maintenance", methods=["GET"])
@role_required("admin")
def get_maintenance():
    mode = MaintenanceMode.query.get(1)
    status = "1" if (mode and mode.is_maintenance) else "0"
    
    response = make_response(jsonify({"enabled": status}))
    
    # Force browser to NOT cache this response
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    return response



@admin_bp.route("/manage-users")
@role_required("admin")
def manage_users():
    all_users = User.query.all()
    return render_template("manage_users.html", users=all_users)
# ... (Keep manual-backup route exactly as it was) ...

@admin_bp.route("/backup-data", methods=["POST"]) # Changed to POST
@role_required("admin")
def backup_data():
    try:
        # 1. Configuration: Save to your projectbackup folder
        BACKUP_DIR = r"C:\Users\yogan\Desktop\projectbackup"
        
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

        # 2. Generate unique filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"Backup_{timestamp}.xlsx"
        full_path = os.path.join(BACKUP_DIR, filename)

        # 3. Write Excel File to Server Disk
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()

        with pd.ExcelWriter(full_path, engine='openpyxl') as writer:
            for table in table_names:
                df = pd.read_sql_table(table, db.engine)
                sheet_name = table[:31]
                df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        print(f">>> SUCCESS: Backup saved locally to {full_path}")

        # 4. Return Success Message (No Download)
        # We only send the filename back, hiding the full path for security
        return jsonify({
            "status": "success", 
            "message": f"Backup '{filename}' created successfully on server."
        })

    except Exception as e:
        print(f">>> Backup Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
    


#======================================================== delete users route@admin_bp.route("/delete-user", methods=["POST"])
@admin_bp.route("/delete-user", methods=["POST"])
@role_required("admin")
def delete_user():
    # Retrieve the username from the hidden form input
    username_to_delete = request.form.get("username")

    if not username_to_delete:
        flash("Error: No username provided.", "danger")
        return redirect(url_for("admin.admin_dashboard"))

    try:
        # Prevent an admin from accidentally deleting themselves
        if username_to_delete == current_user.username:
            flash("Error: You cannot delete your own admin account.", "danger")
            return redirect(url_for("admin.admin_dashboard"))

        # Find the user record
        user = User.query.filter_by(username=username_to_delete).first()

        if user:
            db.session.delete(user)
            db.session.commit()
            flash(f"User {username_to_delete} has been removed.", "success")
        else:
            flash("Error: User not found.", "warning")

    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred: {str(e)}", "danger")

    # Redirect back to the page where the user list is displayed
    return redirect(url_for("admin.admin_dashboard"))



@admin_bp.route("/get-report-options", methods=["GET"])
@role_required("admin")
def get_report_options():
    try:
        # 1. Fetch Distinct Academic Years from 'classes' table
        years_query = db.session.query(Class.academic_year).distinct().all()
        # Flatten list: [('2023-2024',), ('2024-2025',)] -> ['2023-2024', '2024-2025']
        years = [y[0] for y in years_query if y[0]]

        # 2. Fetch All Branches
        branches_query = Branch.query.all()
        branches = [{"id": b.branch_id, "name": b.branch_name} for b in branches_query]

        # 3. Fetch Distinct Semesters (class_name) from 'classes' table
        # Example: 'Semester 1', 'Semester 3'
        sems_query = db.session.query(Class.class_name).distinct().order_by(Class.class_name).all()
        semesters = [s[0] for s in sems_query if s[0]]

        return jsonify({
            "status": "success",
            "years": sorted(years, reverse=True), # Newest year first
            "branches": branches,
            "semesters": semesters
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

##======================================================== report generation route
@admin_bp.route("/generate-report", methods=["POST"])
@role_required("admin")
def generate_report():
    try:
        data = request.get_json()
        
        # Get values
        report_type = data.get("report_type")
        year = data.get("year")
        branch_id = data.get("branch_id")
        semester = data.get("semester")
        file_format = data.get("format", "csv")

        print(f"\n--- REPORT REQUEST ---")
        print(f"Looking for: {report_type} | {year} | Branch {branch_id} | {semester}")

        # 1. Fetch Class ID
        target_class = Class.query.filter_by(
            academic_year=year,
            branch_id=branch_id,
            class_name=semester
        ).first()

        if not target_class:
            print(">>> ERROR: Class not found in database match.")
            return jsonify({"status": "error", "message": "No class found for these selections."}), 404
        
        class_id = target_class.class_id
        print(f">>> SUCCESS: Found Class ID: {class_id}")

        # 2. Fetch Data into DataFrame
        df = None
        
        if report_type == "attendance":
            # FIX 1: Handle Division by Zero using CASE or NULLIF
            query = f"""
                SELECT 
                    s.register_no as 'Register No',
                    s.name as 'Student Name',
                    cp.subject_code as 'Subject',
                    a.total_classes as 'Total Classes',
                    a.classes_attended as 'Classes Attended',
                    CASE 
                        WHEN a.total_classes = 0 THEN 0 
                        ELSE ROUND((a.classes_attended / a.total_classes) * 100, 2) 
                    END as 'Percentage'
                FROM students s
                JOIN attendance a ON s.student_id = a.student_id
                JOIN cie_papers cp ON a.subject_id = cp.paper_id
                WHERE s.class_id = {class_id}
                ORDER BY s.register_no, cp.subject_code;
            """
            df = pd.read_sql(query, db.engine)   
        
        elif report_type == "cie":
            query = f"""
                SELECT 
                    s.register_no as 'Register No',
                    s.name as 'Student Name',
                    cp.subject_code as 'Subject',
                    cm.marks_obtained as 'Marks'
                FROM students s
                JOIN cie_marks cm ON s.student_id = cm.student_id
                JOIN cie_papers cp ON cm.cie_id = cp.paper_id 
                WHERE s.class_id = {class_id}
                ORDER BY s.register_no;
            """
            df = pd.read_sql(query, db.engine)

        # Check if data exists
        if df is None or df.empty:
            print(">>> ERROR: Query returned empty result.")
            return jsonify({"status": "error", "message": "No data found for this report."}), 404

        # 3. Generate File
        output = io.BytesIO()
        mimetype = "text/csv"
        download_name = f"report.{file_format}"

        if file_format == "excel":
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Report')
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            download_name = f"{report_type}_{year}.xlsx"

        elif file_format == "pdf":
            # FIX 2: Safer PDF Generation
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=10)
            
            # Title
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(190, 10, txt=f"{report_type.upper()} REPORT - {year}", ln=True, align='C')
            pdf.ln(10)

            # Table Header
            pdf.set_font("Arial", 'B', 10)
            # Calculate column width dynamically
            col_width = 190 / len(df.columns) if len(df.columns) > 0 else 40
            
            for col in df.columns:
                pdf.cell(col_width, 10, str(col), border=1, align='C')
            pdf.ln()

            # Table Rows
            pdf.set_font("Arial", size=10)
            for i, row in df.iterrows():
                for item in row:
                    # Convert to string and handle potential encoding issues
                    text_val = str(item)
                    try:
                        # Try to encode to latin-1 (required by standard FPDF)
                        text_val.encode('latin-1')
                    except UnicodeEncodeError:
                        # If fails (e.g., emojis or special chars), replace with ?
                        text_val = text_val.encode('latin-1', 'replace').decode('latin-1')
                        
                    pdf.cell(col_width, 10, text_val, border=1, align='C')
                pdf.ln()

            # Output PDF safely
            try:
                # Try standard FPDF approach
                pdf_str = pdf.output(dest='S').encode('latin-1', 'ignore')
                output.write(pdf_str)
            except Exception as e:
                print(f"PDF Output Error: {e}")
                # Fallback for newer FPDF2 versions if needed
                # pdf.output(output) 
                return jsonify({"status": "error", "message": "PDF Generation failed due to library mismatch."}), 500

            mimetype = "application/pdf"
            download_name = f"{report_type}_{year}.pdf"

        else:
            # CSV Fallback
            df.to_csv(output, index=False)
            mimetype = "text/csv"
            download_name = f"{report_type}_{year}.csv"

        output.seek(0)

        return send_file(
            output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )

    except Exception as e:
        print(f">>> CRITICAL REPORT ERROR: {e}")
        # Print the traceback to terminal so you can see exactly line failed
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Server Error: {str(e)}"}), 500

#========================================================       backup upload route=================================
@admin_bp.route("/upload-backup", methods=["POST"])
@role_required("admin")
def upload_backup():
    try:
        # --- UPDATE THIS LINE TO YOUR PREFERRED FOLDER ---
        BACKUP_DIR = r"C:\Users\yogan\Desktop\projectbackup" 
        
        # Ensure directory exists
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)

        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file part"}), 400
            
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400

        if file:
            filename = secure_filename(file.filename)
            save_path = os.path.join(BACKUP_DIR, filename)
            
            file.save(save_path)
            
            # Convert backslashes to forward slashes for the browser message
            display_path = save_path.replace('\\', '/')
            
            print(f">>> SUCCESS: Backup uploaded to {save_path}")
            return jsonify({"status": "success", "message": f"File saved to backup folder"})
            
    except Exception as e:
        print(f">>> Upload Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500