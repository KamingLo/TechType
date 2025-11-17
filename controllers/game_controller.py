# controllers/user_controller.py
from flask import render_template, request, redirect, url_for, flash
from models.user import User
from extensions import db  # Impor db untuk sesi database

# === READ (Semua Users) ===
def users_page():
    """Menampilkan semua user dan form 'Add User'."""
    users = User.query.all()
    return render_template('users.html', users=users)

# === CREATE ===
def add_user():
    """Memproses form 'Add User'."""
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']

        # Cek duplikat
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('Username or email already exists.', 'error')
        else:
            try:
                new_user = User(username=username, email=email)
                db.session.add(new_user)
                db.session.commit()
                flash('User created successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error creating user: {e}', 'error')
                
    return redirect(url_for('users_page'))

# === UPDATE (Halaman Edit) ===
def edit_user_page(user_id):
    """Menampilkan halaman form untuk mengedit user."""
    user = User.query.get_or_404(user_id)
    # Kita perlu template baru untuk ini: edit_user.html
    return render_template('edit_user.html', user=user)

# === UPDATE (Aksi) ===
def update_user_action(user_id):
    """Memproses form 'Edit User'."""
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.username = request.form['username']
        user.email = request.form['email']
        try:
            db.session.commit()
            flash('User updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating user: {e}', 'error')
            
    return redirect(url_for('users_page'))

# === DELETE ===
def delete_user_action(user_id):
    """Menghapus user."""
    user = User.query.get_or_404(user_id)
    try:
        db.session.delete(user)
        db.session.commit()
        flash('User deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {e}', 'error')
        
    return redirect(url_for('users_page'))