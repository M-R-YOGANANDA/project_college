from models.user import User
from utils.password_utils import verify_password


def authenticate_user(username: str, password: str):
    user = User.query.filter_by(username=username).first()

    if not user:
        return None

    # IMPORTANT: password is PLAIN TEXT here
    if not verify_password(password, user.password_hash):
        return None

    if user.is_active is False:
        return None

    return user
