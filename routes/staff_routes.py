from flask import Blueprint, render_template, jsonify, redirect, url_for, request, current_app, send_file
from flask_login import login_required, current_user
from extensions import db
from models import Branch, Class, Batch, Control, Student, Subject, CIEConfig, CIEPapers
from models.staff_allocation import StaffAllocation
from models.attendance import Attendance
from models.cie_marks import CIEMarks
import re
import os
from sqlalchemy import text, func
from io import BytesIO
from datetime import datetime

staff_bp = Blueprint("staff", __name__)

@staff_bp.route("/dashboard")
@login_required
def staff_dashboard():
    if not is_staff():
        return redirect(url_for("auth.login"))
    return render_template("staff.html")


def is_staff():
    return current_user.is_authenticated and (
        getattr(current_user, "role_id", None) == 3 or
        (getattr(current_user, "role", None) and current_user.role.role_name.lower() == "staff")
    )


@staff_bp.route("/dashboard-data")
@login_required
def staff_dashboard_data():
    if not is_staff():
        return jsonify({"error": "Unauthorized"}), 403

    branch = db.session.get(Branch, current_user.branch_id)
    department_name = branch.branch_name if branch else None

    allocations = (
        db.session.query(StaffAllocation, Class, Batch)
        .join(Class, StaffAllocation.class_id == Class.class_id)
        .outerjoin(Batch, StaffAllocation.batch_id == Batch.batch_id)
        .filter(StaffAllocation.staff_id == current_user.user_id)
        .order_by(Class.class_name.asc(), StaffAllocation.subject_name.asc())
        .all()
    )

    allocation_list = []
    staff_semesters = set()
    for alloc, class_, batch in allocations:
        semester = extract_semester_from_class(class_.class_name)
        if semester:
            staff_semesters.add(semester)
        allocation_list.append({
            "allocation_id": alloc.allocation_id,
            "subject_name": alloc.subject_name,
            "class_name": class_.class_name,
            "academic_year": class_.academic_year,
            "batch_name": batch.batch_name if batch else None,
            "semester": semester
        })

    attendance_controls = get_active_controls(current_user.branch_id, "attendance")
    cie_controls = get_active_controls(current_user.branch_id, "cie")

    attendance_enabled = bool(allocations) and control_enabled_for_staff(
        controls=attendance_controls,
        staff_semesters=staff_semesters
    )
    cie_enabled = bool(allocations) and control_enabled_for_staff(
        controls=cie_controls,
        staff_semesters=staff_semesters
    )

    attendance_month = attendance_controls[0].month if attendance_controls else None
    cie_type = cie_controls[0].cie_type if cie_controls else None
    cie_max_marks = None
    cie_number = extract_cie_number(cie_type) if cie_type else None
    if cie_number:
        cie_cfg = CIEConfig.query.filter_by(
            branch_id=current_user.branch_id,
            cie_number=cie_number
        ).first()
        if cie_cfg:
            cie_max_marks = cie_cfg.max_marks

    return jsonify({
        "staff_name": current_user.username,
        "department_name": department_name,
        "role": "Staff",
        "allocations": allocation_list,
        "attendance_enabled": attendance_enabled,
        "cie_enabled": cie_enabled,
        "attendance_control": {
            "month": attendance_month,
            "semesters": sorted([c.semester for c in attendance_controls if c.semester])
        },
        "cie_control": {
            "cie_type": cie_type,
            "max_marks": cie_max_marks,
            "semesters": sorted([c.semester for c in cie_controls if c.semester])
        }
    })


def extract_semester_from_class(class_name):
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


def get_active_controls(branch_id, control_type):
    return Control.query.filter_by(
        branch_id=branch_id,
        control_type=control_type,
        is_active=True
    ).all()


def control_enabled_for_staff(controls, staff_semesters):
    if not controls:
        return False
    if not staff_semesters:
        return True
    return any(
        (c.semester in staff_semesters) or (c.semester is None)
        for c in controls
    )


def extract_cie_number(cie_type):
    if not cie_type:
        return None
    match = re.search(r"(\d+)", cie_type)
    if match:
        return int(match.group(1))
    return None


def normalize_subject_name(name):
    if not name:
        return ""
    cleaned = " ".join(str(name).strip().split())
    cleaned = re.sub(r"\s*[\-\u2022]\s*semester\s*\d+\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*semester\s*\d+\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def normalize_key(value):
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def subject_name_candidates(subject_name):
    if not subject_name:
        return []

    raw = " ".join(str(subject_name).strip().split())
    cleaned = normalize_subject_name(raw)
    candidates = {raw, cleaned}

    for sep in ("•", "-"):
        if sep in cleaned:
            parts = [p.strip() for p in cleaned.split(sep) if p.strip()]
            if parts:
                candidates.add(parts[0])
                candidates.add(parts[-1])

    tokens = cleaned.split()
    if tokens and re.search(r"[A-Za-z]", tokens[0]) and re.search(r"\d", tokens[0]):
        if len(tokens) > 1:
            candidates.add(" ".join(tokens[1:]))

    return [c for c in candidates if c]


def extract_code_candidates(text_value):
    codes = set()
    for token in re.findall(r"[A-Za-z0-9]+", str(text_value or "")):
        if re.search(r"[A-Za-z]", token) and re.search(r"\d", token):
            codes.add(token.upper())
    return codes


def resolve_subject(branch_id, semester, subject_name):
    if not subject_name:
        return None
    candidates = subject_name_candidates(subject_name)
    code_candidates = extract_code_candidates(subject_name)
    candidate_keys = [normalize_key(c) for c in candidates if c]
    code_keys = {normalize_key(c) for c in code_candidates if c}

    def search_subjects(subjects):
        for s in subjects:
            name_key = normalize_key(s.subject_name)
            code_key = normalize_key(s.subject_code)
            for ck in candidate_keys:
                if not ck:
                    continue
                if ck == name_key or ck == code_key:
                    return s
                if ck in name_key or name_key in ck:
                    return s
            for ck in code_keys:
                if ck and ck == code_key:
                    return s
        return None

    q = Subject.query.filter(Subject.branch_id == branch_id)
    if semester:
        q = q.filter(Subject.semester == semester)
    subject = search_subjects(q.all())
    if subject:
        return subject

    # Try across all semesters in the branch as a last resort
    subject = search_subjects(Subject.query.filter(Subject.branch_id == branch_id).all())
    if subject:
        return subject

    return None


def build_staff_report(allocation):
    class_row = db.session.get(Class, allocation.class_id)
    semester = extract_semester_from_class(class_row.class_name if class_row else None)

    subject = resolve_subject(
        branch_id=current_user.branch_id,
        semester=semester,
        subject_name=allocation.subject_name
    )
    if not subject:
        return None, "Subject not found"

    q = Student.query.filter_by(
        class_id=allocation.class_id,
        is_active=True
    )
    if allocation.batch_id:
        q = q.filter_by(batch_id=allocation.batch_id)

    students = q.order_by(Student.register_no.asc()).all()
    if not students:
        return {
            "subject": subject,
            "class_row": class_row,
            "students": []
        }, None

    student_ids = [s.student_id for s in students]

    attendance_rows = Attendance.query.filter(
        Attendance.subject_id == subject.subject_id,
        Attendance.student_id.in_(student_ids)
    ).all()
    attendance_map = {row.student_id: row for row in attendance_rows}

    cie_rows = db.session.query(
        CIEMarks.student_id,
        func.sum(CIEMarks.marks_obtained)
    ).filter(
        CIEMarks.student_id.in_(student_ids),
        CIEMarks.entered_by == current_user.user_id
    ).group_by(CIEMarks.student_id).all()
    cie_map = {sid: int(total or 0) for sid, total in cie_rows}

    results = []
    for s in students:
        att = attendance_map.get(s.student_id)
        total_classes = att.total_classes if att else 0
        classes_attended = att.classes_attended if att else 0
        if total_classes:
            percent = round((classes_attended / total_classes) * 100, 2)
        else:
            percent = 0
        results.append({
            "student_id": s.student_id,
            "register_no": s.register_no,
            "name": s.name,
            "attendance_percent": percent,
            "cie_total": cie_map.get(s.student_id, 0)
        })

    return {
        "subject": subject,
        "class_row": class_row,
        "students": results
    }, None


@staff_bp.route("/staff/allocation-students")
@login_required
def staff_allocation_students():
    if not is_staff():
        return jsonify({"error": "Unauthorized"}), 403

    allocation_id = request.args.get("allocation_id")
    if not allocation_id:
        return jsonify({"error": "allocation_id required"}), 400

    allocation = StaffAllocation.query.filter_by(
        allocation_id=allocation_id,
        staff_id=current_user.user_id
    ).first()

    if not allocation:
        return jsonify({"error": "Allocation not found"}), 404

    q = Student.query.filter_by(
        class_id=allocation.class_id,
        branch_id=current_user.branch_id,
        is_active=True
    )
    if allocation.batch_id:
        q = q.filter_by(batch_id=allocation.batch_id)

    students = q.order_by(Student.register_no.asc()).all()

    return jsonify({
        "students": [
            {
                "student_id": s.student_id,
                "register_no": s.register_no,
                "name": s.name
            } for s in students
        ]
    })


@staff_bp.route("/staff/submit-attendance", methods=["POST"])
@login_required
def submit_attendance():
    if not is_staff():
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json or {}
    allocation_id = data.get("allocation_id")
    total_classes = data.get("total_classes")
    entries = data.get("entries") or []

    if not allocation_id or total_classes is None or str(total_classes).strip() == "":
        return jsonify({"error": "allocation_id and total_classes required"}), 400
    if not entries:
        return jsonify({"error": "No attendance entries provided"}), 400

    allocation = StaffAllocation.query.filter_by(
        allocation_id=allocation_id,
        staff_id=current_user.user_id
    ).first()
    if not allocation:
        return jsonify({"error": "Invalid allocation"}), 400

    class_row = db.session.get(Class, allocation.class_id)
    semester = extract_semester_from_class(class_row.class_name if class_row else None)

    active_controls = get_active_controls(current_user.branch_id, "attendance")
    if not control_enabled_for_staff(active_controls, {semester} if semester else set()):
        return jsonify({"error": "Attendance entry disabled"}), 403

    subject = resolve_subject(
        branch_id=current_user.branch_id,
        semester=semester,
        subject_name=allocation.subject_name
    )
    if not subject:
        return jsonify({"error": "Subject not found"}), 400

    try:
        for entry in entries:
            student_id = entry.get("student_id")
            classes_attended = entry.get("classes_attended")
            if student_id is None or classes_attended is None or str(classes_attended).strip() == "":
                continue

            db.session.execute(
                text("""
                    DELETE FROM attendance
                    WHERE student_id = :sid AND subject_id = :subject_id
                """),
                {"sid": int(student_id), "subject_id": subject.subject_id}
            )
            db.session.execute(
                text("""
                    INSERT INTO attendance
                    (student_id, staff_id, subject_id, total_classes, classes_attended)
                    VALUES (:student_id, :staff_id, :subject_id, :total_classes, :classes_attended)
                    ON DUPLICATE KEY UPDATE
                        staff_id = VALUES(staff_id),
                        subject_id = VALUES(subject_id),
                        total_classes = VALUES(total_classes),
                        classes_attended = VALUES(classes_attended)
                """),
                {
                    "student_id": int(student_id),
                    "staff_id": current_user.user_id,
                    "subject_id": subject.subject_id,
                    "total_classes": int(total_classes),
                    "classes_attended": int(classes_attended)
                }
            )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 500

    return jsonify({"status": "success"})


@staff_bp.route("/staff/submit-cie", methods=["POST"])
@login_required
def submit_cie():
    if not is_staff():
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json or {}
    allocation_id = data.get("allocation_id")
    cie_type = (data.get("cie_type") or "").strip()
    max_marks = data.get("max_marks")
    entries = data.get("entries") or []

    if not allocation_id or not cie_type:
        return jsonify({"error": "allocation_id and cie_type required"}), 400
    if max_marks is None or str(max_marks).strip() == "":
        return jsonify({"error": "max_marks required"}), 400
    if not entries:
        return jsonify({"error": "No CIE entries provided"}), 400

    allocation = StaffAllocation.query.filter_by(
        allocation_id=allocation_id,
        staff_id=current_user.user_id
    ).first()
    if not allocation:
        return jsonify({"error": "Invalid allocation"}), 400

    class_row = db.session.get(Class, allocation.class_id)
    semester = extract_semester_from_class(class_row.class_name if class_row else None)

    active_controls = get_active_controls(current_user.branch_id, "cie")
    if not control_enabled_for_staff(active_controls, {semester} if semester else set()):
        return jsonify({"error": "CIE entry disabled"}), 403

    cie_number = extract_cie_number(cie_type)
    if not cie_number:
        return jsonify({"error": "Invalid CIE type"}), 400

    cie_cfg = CIEConfig.query.filter_by(
        branch_id=current_user.branch_id,
        cie_number=cie_number
    ).first()
    try:
        max_marks_val = int(max_marks)
    except Exception:
        return jsonify({"error": "Invalid max_marks"}), 400

    if not cie_cfg:
        cie_cfg = CIEConfig(
            branch_id=current_user.branch_id,
            cie_number=cie_number,
            max_marks=max_marks_val
        )
        db.session.add(cie_cfg)
        db.session.flush()
    else:
        if max_marks_val and cie_cfg.max_marks != max_marks_val:
            cie_cfg.max_marks = max_marks_val

    try:
        for entry in entries:
            student_id = entry.get("student_id")
            marks = entry.get("marks_obtained")
            if student_id is None or marks is None or str(marks).strip() == "":
                continue

            db.session.execute(
                text("""
                    DELETE FROM cie_marks
                    WHERE student_id = :sid AND cie_id = :cie_id
                """),
                {"sid": int(student_id), "cie_id": cie_cfg.cie_id}
            )
            db.session.execute(
                text("""
                    INSERT INTO cie_marks
                    (student_id, cie_id, marks_obtained, entered_by)
                    VALUES (:student_id, :cie_id, :marks_obtained, :entered_by)
                """),
                {
                    "student_id": int(student_id),
                    "cie_id": cie_cfg.cie_id,
                    "marks_obtained": int(marks),
                    "entered_by": current_user.user_id
                }
            )

        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 500

    return jsonify({"status": "success"})

@staff_bp.route("/staff/upload-cie-paper", methods=["POST"])
@login_required
def upload_cie_paper():
    if not is_staff():
        return jsonify({"error": "Unauthorized"}), 403

    allocation_id = (request.form.get("allocation_id") or "").strip()
    file = request.files.get("file")

    if not allocation_id:
        return jsonify({"error": "allocation_id required"}), 400
    if not file or not file.filename:
        return jsonify({"error": "PDF file required"}), 400

    filename_lower = file.filename.lower()
    if not filename_lower.endswith(".pdf"):
        return jsonify({"error": "Only PDF files are allowed"}), 400

    allocation = StaffAllocation.query.filter_by(
        allocation_id=allocation_id,
        staff_id=current_user.user_id
    ).first()
    if not allocation:
        return jsonify({"error": "Invalid allocation"}), 400

    class_row = db.session.get(Class, allocation.class_id)
    semester = extract_semester_from_class(class_row.class_name if class_row else None)
    if not semester:
        return jsonify({"error": "Unable to determine semester"}), 400

    subject = resolve_subject(
        branch_id=current_user.branch_id,
        semester=semester,
        subject_name=allocation.subject_name
    )
    if not subject:
        return jsonify({"error": "Subject not found"}), 400

    subject_code = subject.subject_code
    academic_year = class_row.academic_year if class_row else ""

    subject_for_name = subject.subject_name or subject_code
    safe_subject = re.sub(r"[^a-zA-Z0-9]+", "_", subject_for_name).strip("_")
    safe_year = re.sub(r"[^a-zA-Z0-9]+", "_", academic_year).strip("_")
    
    if safe_year:
        final_name = f"{semester}_{safe_subject}_{safe_year}.pdf"
    else:
        final_name = f"{semester}_{safe_subject}.pdf"

    # --- 1. DEFINE BASE PATH ---
    # Using raw string for Windows path compatibility
    base_path = r"C:\Users\yogan\Desktop\projectbackup"
    
    # --- 2. CONSTRUCT FULL PATH ---
    # Result: C:\Users\yogan\Desktop\projectbackup\static\uploads\cie_papers\semester_X
    upload_dir = os.path.join(base_path, "static", "uploads", "cie_papers", f"semester_{semester}")
    
    os.makedirs(upload_dir, exist_ok=True)
    
    # This is the full absolute path including filename
    file_path = os.path.join(upload_dir, final_name)

    # --- 3. SAVE FILE TO THAT PATH ---
    file.save(file_path)

    try:
        paper = CIEPapers(
            staff_id=current_user.user_id,
            branch_id=current_user.branch_id,
            semester=semester,
            # --- 4. INSERT ABSOLUTE PATH INTO DB ---
            # We use 'file_path' here instead of a relative string
            file_path=file_path, 
            subject_code=subject_code,
            is_displayed=0
        )
        db.session.add(paper)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 500

    return jsonify({"status": "success", "file_path": file_path})


@staff_bp.route("/staff/report-data")
@login_required
def staff_report_data():
    if not is_staff():
        return jsonify({"error": "Unauthorized"}), 403

    allocation_id = request.args.get("allocation_id")
    if not allocation_id:
        return jsonify({"error": "allocation_id required"}), 400

    allocation = StaffAllocation.query.filter_by(
        allocation_id=allocation_id,
        staff_id=current_user.user_id
    ).first()
    if not allocation:
        return jsonify({"error": "Invalid allocation"}), 400

    report, error = build_staff_report(allocation)
    if error:
        return jsonify({"error": error}), 400

    subject = report["subject"]
    class_row = report["class_row"]

    return jsonify({
        "subject_name": subject.subject_name,
        "subject_code": subject.subject_code,
        "semester": extract_semester_from_class(class_row.class_name if class_row else None),
        "academic_year": class_row.academic_year if class_row else None,
        "students": report["students"]
    })


@staff_bp.route("/staff/report-pdf")
@login_required
def staff_report_pdf():
    if not is_staff():
        return jsonify({"error": "Unauthorized"}), 403

    allocation_id = request.args.get("allocation_id")
    if not allocation_id:
        return jsonify({"error": "allocation_id required"}), 400

    allocation = StaffAllocation.query.filter_by(
        allocation_id=allocation_id,
        staff_id=current_user.user_id
    ).first()
    if not allocation:
        return jsonify({"error": "Invalid allocation"}), 400

    report, error = build_staff_report(allocation)
    if error:
        return jsonify({"error": error}), 400

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
    except Exception:
        return jsonify({"error": "PDF generator not installed. Please install reportlab."}), 500

    subject = report["subject"]
    class_row = report["class_row"]
    semester = extract_semester_from_class(class_row.class_name if class_row else None)
    academic_year = class_row.academic_year if class_row else ""
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M")

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24)
    styles = getSampleStyleSheet()

    elements = [
        Paragraph("CPC Polytechnic Mysuru", styles["Title"]),
        Paragraph(f"Attendance & CIE Report - {subject.subject_name}", styles["Heading2"]),
        Paragraph(f"Semester: {semester or '--'} | Academic Year: {academic_year} | Generated: {now_text}", styles["Normal"]),
        Spacer(1, 12)
    ]

    table_data = [["Reg No", "Student Name", "Attendance %", "CIE Marks"]]
    for s in report["students"]:
        table_data.append([
            s["register_no"],
            s["name"],
            f"{s['attendance_percent']}%",
            str(s["cie_total"])
        ])

    if len(table_data) == 1:
        table_data.append(["--", "No data", "--", "--"])

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (2, 1), (3, -1), "CENTER"),
    ]))

    elements.append(table)
    doc.build(elements)
    buffer.seek(0)

    safe_subject = re.sub(r"[^a-zA-Z0-9]+", "_", subject.subject_name).strip("_")
    filename = f"report_{semester}_{safe_subject}.pdf"

    return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")
