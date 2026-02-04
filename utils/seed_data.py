from extensions.db import db
from models.role import Role
from models.branch import Branch


def seed_roles():
    roles = [
        {"role_id": 1, "role_name": "ADMIN"},
        {"role_id": 2, "role_name": "HOD"},
        {"role_id": 3, "role_name": "STAFF"},
    ]

    for r in roles:
        existing = Role.query.filter(
            (Role.role_id == r["role_id"]) |
            (Role.role_name == r["role_name"])
        ).first()

        if not existing:
            db.session.add(
                Role(
                    role_id=r["role_id"],
                    role_name=r["role_name"]
                )
            )

    db.session.commit()
    print("✅ Roles verified (ADMIN=1, HOD=2, STAFF=3)")


def seed_branches():
    branches = [
        {"branch_code": "CSE", "branch_name": "Computer Science and Engineering"},
        {"branch_code": "ECE", "branch_name": "Electronics and Communication Engineering"},
    ]

    for b in branches:
        existing = Branch.query.filter_by(branch_code=b["branch_code"]).first()
        if not existing:
            db.session.add(
                Branch(
                    branch_code=b["branch_code"],
                    branch_name=b["branch_name"]
                )
            )

    db.session.commit()
    print("✅ Branches seeded")


def run_seed():
    seed_roles()
    seed_branches()
