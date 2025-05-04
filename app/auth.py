"""
Authentication module for ChitUI
"""
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from loguru import logger
import uuid
from datetime import datetime
from app.models import db, User

# Create blueprint
auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login."""
    # If user is already logged in, redirect to home
    if current_user.is_authenticated:
        return redirect(url_for('routes.index'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = 'remember' in request.form

        # Find user by username
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            # Update last login time
            user.last_login = datetime.utcnow()
            db.session.commit()

            login_user(user, remember=remember)
            logger.info(f"User {username} logged in")

            # Redirect to the page the user was trying to access
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('routes.index'))
        else:
            error = "Invalid username or password"
            logger.warning(f"Failed login attempt for username: {username}")

    return render_template('login.html', error=error)


@auth_bp.route('/logout')
@login_required
def logout():
    """Handle user logout."""
    logger.info(f"User {current_user.username} logged out")
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/users', methods=['GET'])
@login_required
def list_users():
    """List all users (admin only)."""
    if not current_user.is_admin():
        flash("You don't have permission to access this page.", "danger")
        return redirect(url_for('routes.index'))

    users = User.query.all()
    return render_template('admin.html',
                           users=users,
                           current_user=current_user,
                           user=current_user)


@auth_bp.route('/users/add', methods=['POST'])
@login_required
def add_user():
    """Add a new user (admin only)."""
    if not current_user.is_admin():
        flash("You don't have permission to perform this action.", "danger")
        return redirect(url_for('routes.index'))

    username = request.form.get('username')
    password = request.form.get('password')
    role = request.form.get('role', 'user')

    # Check if username already exists
    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        flash(f"Username '{username}' already exists.", "danger")
        return redirect(url_for('auth.list_users'))

    # Create user
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        password=password,
        role=role
    )

    db.session.add(user)
    db.session.commit()

    logger.info(f"User '{username}' created by admin: {current_user.username}")
    flash(f"User '{username}' created successfully.", "success")
    return redirect(url_for('auth.list_users'))


@auth_bp.route('/users/<user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """Delete a user (admin only)."""
    if not current_user.is_admin():
        flash("You don't have permission to perform this action.", "danger")
        return redirect(url_for('routes.index'))

    # Prevent deleting self
    if user_id == current_user.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for('auth.list_users'))

    # Delete user
    user = User.query.get(user_id)
    if user:
        username = user.username
        db.session.delete(user)
        db.session.commit()
        logger.info(
            f"User '{username}' deleted by admin: {current_user.username}")
        flash(f"User '{username}' deleted successfully.", "success")
    else:
        flash("User not found.", "danger")

    return redirect(url_for('auth.list_users'))


@auth_bp.route('/users/<user_id>/reset-password', methods=['POST'])
@login_required
def reset_password(user_id):
    """Reset a user's password (admin only or own account)."""
    if not current_user.is_admin() and user_id != current_user.id:
        flash("You don't have permission to perform this action.", "danger")
        return redirect(url_for('routes.index'))

    password = request.form.get('password')

    user = User.query.get(user_id)
    if user:
        user.set_password(password)
        db.session.commit()
        logger.info(
            f"Password reset for user '{user.username}' by: {current_user.username}")
        flash("Password updated successfully.", "success")
    else:
        flash("User not found.", "danger")

    if current_user.is_admin():
        return redirect(url_for('auth.list_users'))
    else:
        return redirect(url_for('routes.index'))


@auth_bp.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    """User account management."""
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Validate input
        if not current_password or not new_password or not confirm_password:
            flash("All fields are required.", "danger")
        elif not current_user.check_password(current_password):
            flash("Current password is incorrect.", "danger")
        elif new_password != confirm_password:
            flash("New passwords do not match.", "danger")
        else:
            # Update password
            current_user.set_password(new_password)
            db.session.commit()
            logger.info(
                f"User '{current_user.username}' changed their password")
            flash("Password updated successfully.", "success")
            return redirect(url_for('routes.index'))

    return render_template('account.html', user=current_user)
