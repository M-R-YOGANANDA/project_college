from flask import Blueprint, render_template, request, jsonify, send_file, current_app
from flask_login import login_required, current_user
from sqlalchemy import text, func
from extensions import db
from models import (
    User, Student, Class, Batch,
    StaffAllocation, CIEPapers, Control, Subject,
    Attendance, CIEMarks, CIEConfig
)
import os
import re
import pandas as pd
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

hod_bp = Blueprint("hod", __name__, url_prefix="/hod")

# =========================================================
# HELPERS
# =========================================================

def semester_class_name(sem):
    try:
        sem = int(sem)
    except Exception:
        return ""
    if sem == 1:
        return "1st Semester"
    if sem == 2:
        return "2nd Semester"
    if sem == 3:
        return "3rd Semester"
    return f"{sem}th Semester"


def extract_semester_from_class_name(class_name):
    if not class_name:
        return None
    digit_match = re.search(r"([1-8])", class_name)
    if digit_match:
        return int(digit_match.group(1))
    roman_map = {
        "i": 1,
        "ii": 2,
        "iii": 3,
        "iv": 4,
        "v": 5,
        "vi": 6,
        "vii": 7,
        "viii": 8
    }
    roman_match = re.search(r"\b(i{1,3}|iv|v|vi|vii|viii)\b", class_name, re.IGNORECASE)
    if roman_match:
        return roman_map.get(roman_match.group(1).lower())
    return None


def find_class_for_semester(branch_id, sem_value):
    target_name = semester_class_name(sem_value)
    target_class = Class.query.filter_by(
        branch_id=branch_id,
        class_name=target_name
    ).first()
    if target_class:
        return target_class

    # Fallback: match by numeric semester inside class_name
    classes = Class.query.filter_by(branch_id=branch_id).all()
    for c in classes:
        if extract_semester_from_class_name(c.class_name) == sem_value:
            return c
    return None


def get_class_id_for_sem(branch_id, semester_val, year=None):
    """
    Robust way to find a class_id given a numeric semester.
    Optionally filter by academic year.
    """
    try:
        sem_num = int(semester_val)
    except Exception:
        return None

    query = Class.query.filter(Class.branch_id == branch_id)
    if year:
        query = query.filter(Class.academic_year == year)

    classes = query.all()
    for c in classes:
        extracted = extract_semester_from_class_name(c.class_name)
        if extracted is not None and int(extracted) == sem_num:
            return c.class_id
    return None

def is_hod():
    return (
        current_user.is_authenticated and
        hasattr(current_user, "role") and
        current_user.role.role_name.lower() == "hod"
    )


def hod_only():
    if not is_hod():
        return jsonify({"error": "Unauthorized"}), 403
    return None


# =========================================================
# DASHBOARD
# =========================================================

@hod_bp.route("/dashboard")
@login_required
def dashboard():
    if not is_hod():
        return "Unauthorized", 403
    return render_template("hod.html")


@hod_bp.route("/dashboard-stats")
@login_required
def dashboard_stats():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    branch_id = current_user.branch_id

    student_count = Student.query.filter_by(branch_id=branch_id).count()

    staff_count = (
        db.session.query(User)
        .join(User.role)
        .filter(
            User.branch_id == branch_id,
            text("roles.role_name = 'staff'")
        )
        .count()
    )

    attendance_enabled = Control.query.filter_by(
        branch_id=branch_id,
        control_type="attendance",
        is_active=True
    ).first() is not None

    cie_enabled = Control.query.filter_by(
        branch_id=branch_id,
        control_type="cie",
        is_active=True
    ).first() is not None

    return jsonify({
        "hod_name": current_user.username,
        "student_count": student_count,
        "staff_count": staff_count,
        "attendance_status": {"enabled": attendance_enabled},
        "cie_status": {"enabled": cie_enabled}
    })

@hod_bp.route("/get-dropdown-data")
@login_required
def get_dropdown_data():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    branch_id = current_user.branch_id

    years = (
        db.session.query(Class.academic_year)
        .filter(Class.branch_id == branch_id)
        .distinct()
        .all()
    )

    extracted_years = [y[0] for y in years if y[0]]

    classes = Class.query.filter_by(branch_id=branch_id).all()
    semesters = set()
    for c in classes:
        sem = extract_semester_from_class_name(c.class_name)
        if sem is not None:
            semesters.add(int(sem))

    return jsonify({
        "years": sorted(extracted_years, reverse=True),
        "semesters": sorted(list(semesters))
    })

# =========================================================
# STUDENT MANAGEMENT
# =========================================================

@hod_bp.route("/students")
@login_required
def list_students():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    q = text("""
        SELECT s.student_id, s.register_no, s.name, c.class_name
        FROM students s
        JOIN classes c ON s.class_id = c.class_id
        WHERE s.branch_id = :bid
        ORDER BY s.register_no
    """)

    rows = db.session.execute(q, {"bid": current_user.branch_id}).fetchall()

    return jsonify([
        {
            "student_id": r[0],
            "register_no": r[1],
            "name": r[2],
            "semester": r[3]
        } for r in rows
    ])


@hod_bp.route("/add-student", methods=["POST"])
@login_required
def add_student():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    data = request.json or {}
    reg_no = (data.get("register_no") or "").strip()
    name = (data.get("name") or "").strip()
    sem_val = data.get("semester")

    if not reg_no or not name or not sem_val:
        return jsonify({"error": "Register Number, Name, and Semester are required."}), 400

    if Student.query.filter_by(register_no=reg_no).first():
        return jsonify({"error": f"Register Number {reg_no} already exists!"}), 400

    sem_numeric = parse_semester_value(sem_val)
    if not sem_numeric:
        return jsonify({"error": f"Invalid semester value: {sem_val}"}), 400

    target_class = None
    name_a = semester_class_name(sem_numeric)
    if name_a:
        target_class = Class.query.filter_by(
            branch_id=current_user.branch_id,
            class_name=name_a
        ).first()

    if not target_class:
        target_class = find_class_for_semester(current_user.branch_id, sem_numeric)

    if not target_class:
        return jsonify({"error": f"Could not find a Class for Semester {sem_val}."}), 400

    try:
        student = Student(
            register_no=reg_no,
            name=name,
            branch_id=current_user.branch_id,
            class_id=target_class.class_id,
            is_active=1
        )
        db.session.add(student)
        db.session.commit()
        return jsonify({"status": "success", "message": "Student added successfully!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@hod_bp.route("/delete-student/<register_no>", methods=["DELETE"])
@login_required
def delete_student(register_no):
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    student = Student.query.filter_by(register_no=register_no).first()
    if not student:
        return jsonify({"error": "Student not found"}), 404

    db.session.delete(student)
    db.session.commit()

    return jsonify({"status": "deleted"})

@hod_bp.route("/update-students", methods=["POST"])
@login_required
def update_students():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    data = request.json or {}
    students_list = data.get("students", [])

    try:
        for s in students_list:
            student_id = s.get("student_id")
            new_reg = s.get("register_no")
            new_name = s.get("name")
            new_sem = s.get("semester")

            if not student_id:
                continue

            student = Student.query.filter_by(student_id=student_id).first()
            if not student:
                continue

            if new_reg and new_reg != student.register_no:
                if not Student.query.filter_by(register_no=new_reg).first():
                    student.register_no = new_reg

            if new_name:
                student.name = new_name

            if new_sem:
                sem_numeric = parse_semester_value(new_sem)
                if sem_numeric:
                    target_class = Class.query.filter_by(
                        branch_id=current_user.branch_id,
                        class_name=semester_class_name(sem_numeric)
                    ).first()
                    if not target_class:
                        target_class = find_class_for_semester(current_user.branch_id, sem_numeric)
                    if target_class:
                        student.class_id = target_class.class_id

        db.session.commit()
        return jsonify({"status": "success", "message": "Students updated successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# =========================================================
# BULK UPLOAD MODULE
# =========================================================

@hod_bp.route("/download-student-template")
@login_required
def download_student_template():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    headers = ["Register Number", "Student Name", "Semester", "Batch"]
    df = pd.DataFrame(columns=headers)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Students")

    output.seek(0)

    return send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="student_upload_template.xlsx"
    )


def parse_semester_value(value):
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except Exception:
        match = re.search(r"(\d+)", str(value))
        if match:
            return int(match.group(1))
    return None


@hod_bp.route("/upload-student-list", methods=["POST"])
@login_required
def upload_student_list():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.lower().endswith(".xlsx"):
        return jsonify({"error": "Invalid file format. Only .xlsx files are accepted."}), 400

    try:
        df = pd.read_excel(file)
        df.columns = [c.strip() for c in df.columns]

        required_cols = ["Register Number", "Student Name", "Semester"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            return jsonify({"error": f"Missing columns: {', '.join(missing)}"}), 400

        success_count = 0
        errors = []

        for index, row in df.iterrows():
            if pd.isna(row.get("Register Number")) or pd.isna(row.get("Student Name")) or pd.isna(row.get("Semester")):
                continue

            reg_no = str(row["Register Number"]).strip()
            name = str(row["Student Name"]).strip()
            sem_value = parse_semester_value(row["Semester"])
            batch_raw = str(row.get("Batch", "")).strip()

            if not reg_no or not name or not sem_value:
                continue

            if Student.query.filter_by(register_no=reg_no).first():
                errors.append(f"Row {index+2}: Register No {reg_no} already exists.")
                continue

            target_class = find_class_for_semester(current_user.branch_id, sem_value)

            if not target_class:
                errors.append(f"Row {index+2}: Semester '{sem_value}' not found for this branch.")
                continue

            batch_id = None
            if batch_raw:
                batch = Batch.query.filter_by(
                    class_id=target_class.class_id,
                    batch_name=batch_raw
                ).first()
                if batch:
                    batch_id = batch.batch_id

            new_student = Student(
                register_no=reg_no,
                name=name,
                branch_id=current_user.branch_id,
                class_id=target_class.class_id,
                batch_id=batch_id,
                is_active=True
            )
            db.session.add(new_student)
            success_count += 1

        db.session.commit()

        message = f"Successfully added {success_count} students."
        if errors:
            message += f" {len(errors)} errors occurred (first 3: {', '.join(errors[:3])})."

        return jsonify({"status": "success", "message": message})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Processing failed: {str(e)}"}), 500


# =========================================================
# COURSE MANAGEMENT
# =========================================================

@hod_bp.route("/add-course", methods=["POST"])
@login_required
def add_course():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    data = request.json or {}

    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip()
    syllabus = (data.get("syllabus") or "").strip()
    semester_val = data.get("semester")

    if not all([name, code, syllabus, semester_val]):
        return jsonify({"error": "All fields (Name, Code, Syllabus, Semester) are required"}), 400

    if Subject.query.filter_by(subject_code=code).first():
        return jsonify({"error": f"Course Code '{code}' already exists."}), 400

    try:
        new_subject = Subject(
            subject_name=name,
            subject_code=code,
            syllabus_name=syllabus,
            semester=int(semester_val),
            branch_id=current_user.branch_id,
            is_active=1
        )

        db.session.add(new_subject)
        db.session.commit()

        return jsonify({"status": "success", "message": "Course added successfully!"})
    except ValueError:
        return jsonify({"error": "Semester must be a valid number."}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Database Error: {str(e)}"}), 500

# =========================================================
# STAFF ALLOCATION
# =========================================================

@hod_bp.route("/get-staff-list")
@login_required
def get_staff_list():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    query = text("""
        SELECT u.username
        FROM users u
        JOIN roles r ON u.role_id = r.role_id
        WHERE u.branch_id = :bid
          AND r.role_name = 'staff'
        ORDER BY u.username
    """)

    rows = db.session.execute(query, {"bid": current_user.branch_id}).fetchall()
    return jsonify([row[0] for row in rows])

@hod_bp.route("/allocations")
@login_required
def list_allocations():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    q = text("""
        SELECT 
            c.class_name,
            sa.subject_name,
            s.subject_code,
            u.username,
            b.batch_name,
            sa.allocation_id
        FROM staff_allocations sa
        JOIN users u ON sa.staff_id = u.user_id
        JOIN classes c ON sa.class_id = c.class_id
        LEFT JOIN batches b ON sa.batch_id = b.batch_id
        LEFT JOIN subjects s ON sa.subject_name = s.subject_name AND s.branch_id = c.branch_id
        WHERE c.branch_id = :bid
        ORDER BY c.class_name, sa.subject_name
    """)

    rows = db.session.execute(q, {"bid": current_user.branch_id}).fetchall()

    data = []
    for r in rows:
        type_str = "Theory"
        if r[4]:
            type_str = f"Lab (Batch {r[4]})"
        subject_code = r[2]
        if not subject_code:
            sem_num = extract_semester_from_class_name(r[0])
            subj_q = Subject.query.filter_by(
                branch_id=current_user.branch_id,
                subject_name=r[1]
            )
            if sem_num:
                subj_q = subj_q.filter_by(semester=sem_num)
            subj = subj_q.first()
            if subj:
                subject_code = subj.subject_code
        data.append({
            "semester": r[0],
            "subject": r[1],
            "code": subject_code if subject_code else "--",
            "staff": r[3],
            "type": type_str,
            "id": r[5]
        })

    return jsonify(data)


@hod_bp.route("/create-allocation", methods=["POST"])
@login_required
def create_allocation():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    data = request.json or {}
    branch_id = current_user.branch_id

    staff_user = User.query.filter_by(
        username=data.get("staff"),
        branch_id=branch_id
    ).join(User.role).filter(text("roles.role_name='staff'")).first()

    if not staff_user:
        return jsonify({"error": "Staff not found"}), 400

    class_id = get_class_id_for_sem(branch_id, data.get("sem"))
    if not class_id:
        return jsonify({"error": f"No class found for Semester {data.get('sem')}"}), 400

    batch_id = None
    if "lab" in (data.get("type") or "").lower():
        type_val = (data.get("type") or "").lower()
        batch_name = "B" if "-b" in type_val else "A"
        batch = Batch.query.filter_by(
            class_id=class_id,
            batch_name=batch_name
        ).first()
        if not batch:
            batch = Batch(class_id=class_id, batch_name=batch_name)
            db.session.add(batch)
            db.session.commit()
        batch_id = batch.batch_id

    # Prevent exact duplicates
    existing = StaffAllocation.query.filter_by(
        staff_id=staff_user.user_id,
        class_id=class_id,
        batch_id=batch_id,
        subject_name=data.get("subject")
    ).first()

    if existing:
        return jsonify({"error": "Allocation already exists"}), 400

    alloc = StaffAllocation(
        staff_id=staff_user.user_id,
        class_id=class_id,
        batch_id=batch_id,
        subject_name=data.get("subject")
    )

    db.session.add(alloc)
    db.session.commit()

    return jsonify({"status": "success"})

@hod_bp.route("/get-subjects-by-sem")
@login_required
def get_subjects_by_sem():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    sem = request.args.get("semester")
    if not sem:
        return jsonify({"status": "error", "message": "Semester required"}), 400

    subjects = Subject.query.filter_by(
        branch_id=current_user.branch_id,
        semester=sem,
        is_active=True
    ).all()

    return jsonify({
        "status": "success",
        "subjects": [
            {"name": s.subject_name, "code": s.subject_code}
            for s in subjects
        ]
    })

# =========================================================
# CONTROLLERS (ATTENDANCE / CIE)
# =========================================================

@hod_bp.route("/update-control", methods=["POST"])
@login_required
def update_control():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    data = request.json or {}

    control_type = data.get("type")
    enabled = bool(data.get("enabled"))
    details = data.get("details") or {}

    if control_type not in ("attendance", "cie"):
        return jsonify({"status": "error", "message": "Invalid control type"}), 400

    if not enabled:
        Control.query.filter_by(
            branch_id=current_user.branch_id,
            control_type=control_type
        ).update({Control.is_active: False})
        db.session.commit()
        return jsonify({"status": "success"})

    semesters = details.get("semesters") or []
    if control_type == "attendance":
        month = details.get("month")
        if not month or not semesters:
            return jsonify({"status": "error", "message": "Month and semesters are required"}), 400

        Control.query.filter_by(
            branch_id=current_user.branch_id,
            control_type="attendance"
        ).update({Control.is_active: False})

        for sem in semesters:
            sem_val = int(sem)
            existing = Control.query.filter_by(
                branch_id=current_user.branch_id,
                control_type="attendance",
                month=str(month),
                semester=sem_val
            ).first()
            if existing:
                existing.is_active = True
            else:
                db.session.add(Control(
                    branch_id=current_user.branch_id,
                    control_type="attendance",
                    month=str(month),
                    semester=sem_val,
                    is_active=True
                ))

    if control_type == "cie":
        cie_type = (details.get("cie_type") or "").strip()
        if not cie_type or not semesters:
            return jsonify({"status": "error", "message": "CIE type and semesters are required"}), 400

        Control.query.filter_by(
            branch_id=current_user.branch_id,
            control_type="cie"
        ).update({Control.is_active: False})

        for sem in semesters:
            sem_val = int(sem)
            existing = Control.query.filter_by(
                branch_id=current_user.branch_id,
                control_type="cie",
                cie_type=cie_type,
                semester=sem_val
            ).first()
            if existing:
                existing.is_active = True
            else:
                db.session.add(Control(
                    branch_id=current_user.branch_id,
                    control_type="cie",
                    cie_type=cie_type,
                    semester=sem_val,
                    is_active=True
                ))

    db.session.commit()
    return jsonify({"status": "success"})


# =========================================================
# CIE PAPERS (VIEW ONLY)
# =========================================================

@hod_bp.route("/cie-uploads")
@login_required
def cie_uploads():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    papers = (
        db.session.query(CIEPapers, User, Subject)
        .join(User, CIEPapers.staff_id == User.user_id)
        .outerjoin(
            Subject,
            (Subject.subject_code == CIEPapers.subject_code) &
            (Subject.branch_id == CIEPapers.branch_id)
        )
        .filter(
            CIEPapers.branch_id == current_user.branch_id,
            User.branch_id == current_user.branch_id,
            CIEPapers.is_displayed == 0
        )
        .order_by(CIEPapers.uploaded_at.desc())
        .all()
    )

    return jsonify([
        {
            "semester": paper.semester,
            "subject_code": paper.subject_code,
            "subject_name": subject.subject_name if subject else None,
            "staff": user.username,
            "uploaded_at": paper.uploaded_at.strftime("%Y-%m-%d %H:%M:%S") if paper.uploaded_at else None,
            "id": paper.paper_id
        } for paper, user, subject in papers
    ])

@hod_bp.route("/clear-cie-list", methods=["POST"])
@login_required
def clear_cie_list():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    CIEPapers.query.filter_by(branch_id=current_user.branch_id).update({CIEPapers.is_displayed: 1})
    db.session.commit()
    return jsonify({"status": "success"})

@hod_bp.route("/download-paper/<int:paper_id>")
@login_required
def download_cie_paper(paper_id):
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    paper = CIEPapers.query.filter_by(
        paper_id=paper_id,
        branch_id=current_user.branch_id
    ).first()
    if not paper:
        return jsonify({"error": "Paper not found"}), 404

    file_path = paper.file_path
    if not os.path.isabs(file_path):
        file_path = os.path.join(current_app.root_path, file_path)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found on server"}), 404

    return send_file(file_path, as_attachment=True)

# =========================================================
# REPORTS MODULE
# =========================================================

def fetch_report_data(report_type, year, semester, subject_name=None, branch_id=None):
    """
    Robust data fetching that handles the missing subject_id in cie_marks
    by linking through staff allocations.
    """
    try:
        target_classes = Class.query.filter(
            Class.branch_id == branch_id,
            Class.academic_year == year
        ).all()

        class_ids = []
        for c in target_classes:
            match = re.search(r"(\d+)", c.class_name or "")
            if match and int(match.group(1)) == int(semester):
                class_ids.append(c.class_id)

        if not class_ids:
            print(f"DEBUG: No classes found for Year: {year}, Sem: {semester}")
            return []

        data = []

        if report_type == "cie":
            query = db.session.query(
                Student.register_no,
                Student.name,
                func.sum(CIEMarks.marks_obtained).label("total"),
                func.sum(CIEConfig.max_marks).label("max")
            ).select_from(Student) \
             .join(CIEMarks, Student.student_id == CIEMarks.student_id) \
             .join(CIEConfig, CIEMarks.cie_id == CIEConfig.cie_id) \
             .filter(Student.class_id.in_(class_ids))

            if subject_name:
                query = query.join(
                    StaffAllocation,
                    (CIEMarks.entered_by == StaffAllocation.staff_id) &
                    (Student.class_id == StaffAllocation.class_id)
                ).filter(StaffAllocation.subject_name == subject_name)

            results = query.group_by(Student.student_id).all()

            for r in results:
                max_m = r.max if r.max else 0
                obt_m = r.total if r.total else 0
                percentage = (obt_m / max_m * 100) if max_m > 0 else 0
                grade = "Pass" if percentage >= 35 else "Fail"
                data.append({
                    "register_no": r.register_no,
                    "name": r.name,
                    "marks": f"{int(obt_m)}/{int(max_m)}",
                    "grade": grade
                })

        elif report_type == "attendance":
            query = db.session.query(
                Student.register_no,
                Student.name,
                Attendance.total_classes,
                Attendance.classes_attended
            ).select_from(Student) \
             .join(Attendance, Student.student_id == Attendance.student_id) \
             .filter(Student.class_id.in_(class_ids))

            if subject_name:
                subj_obj = Subject.query.filter_by(
                    subject_name=subject_name,
                    branch_id=branch_id
                ).first()
                if subj_obj:
                    query = query.filter(Attendance.subject_id == subj_obj.subject_id)
                else:
                    print(f"DEBUG: Subject '{subject_name}' not found in Subjects table.")
                    return []

            results = query.all()

            for r in results:
                total = r.total_classes if r.total_classes else 0
                attended = r.classes_attended if r.classes_attended else 0
                percentage = (attended / total * 100) if total > 0 else 0
                status = "Good" if percentage >= 75 else "Shortage"
                data.append({
                    "register_no": r.register_no,
                    "name": r.name,
                    "marks": f"{int(percentage)}%",
                    "grade": status
                })

        return data

    except Exception as e:
        print(f"CRITICAL DB ERROR in fetch_report_data: {str(e)}")
        raise e


@hod_bp.route("/generate-report-data")
@login_required
def generate_report_data():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    try:
        r_type = request.args.get("type")
        year = request.args.get("year")
        sem = request.args.get("semester")
        subject = request.args.get("subject")

        print(f"Generating Report: Type={r_type}, Year={year}, Sem={sem}, Sub={subject}")

        if not all([r_type, year, sem]):
            return jsonify({"status": "error", "message": "Missing required filters"}), 400

        data = fetch_report_data(r_type, year, sem, subject, current_user.branch_id)

        return jsonify({"status": "success", "data": data})
    except Exception as e:
        print(f"ROUTE ERROR: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@hod_bp.route("/download-report-pdf")
@login_required
def download_report_pdf():
    unauthorized = hod_only()
    if unauthorized:
        return unauthorized

    r_type = request.args.get("type")
    year = request.args.get("year")
    sem = request.args.get("semester")
    subject = request.args.get("subject")

    data = fetch_report_data(r_type, year, sem, subject, current_user.branch_id)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    title = f"{r_type.upper()} Report - {year} (Sem {sem})"
    if subject:
        title += f" - {subject}"
    elements.append(Paragraph(title, styles["Title"]))
    elements.append(Spacer(1, 12))

    table_data = [["Register No", "Name", "Score/Percentage", "Status"]]
    for row in data:
        table_data.append([row["register_no"], row["name"], row["marks"], row["grade"]])

    t = Table(table_data)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(t)
    doc.build(elements)

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"report_{r_type}_{year}_{sem}.pdf",
        mimetype="application/pdf"
    )
