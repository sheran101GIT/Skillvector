from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from .models import User
from .db import db

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        # Allow login by username or email
        user = User.query.filter((User.username == username) | (User.email == username)).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('main.dashboard'))
        else:
            flash('Invalid username or password')
            
    return render_template('login.html')

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name')
        
        user = User.query.filter((User.username == username) | (User.email == email)).first()
        if user:
            flash('Email or username already exists')
            return redirect(url_for('auth.register'))
            
        from werkzeug.security import generate_password_hash
        new_user = User(email=email, username=username, name=name, password_hash=generate_password_hash(password))
        
        db.session.add(new_user)
        db.session.commit()
        
        login_user(new_user)
        return redirect(url_for('main.dashboard'))
        
    return render_template('register.html')

@auth.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        
        # Check if email is taken by another user
        existing_user = User.query.filter(User.email == email).first()
        if existing_user and existing_user.id != current_user.id:
            flash('Email already in use by another account.')
            return redirect(url_for('auth.edit_profile'))
            
        current_user.name = name
        current_user.email = email
        
        try:
            db.session.commit()
            flash('Profile updated successfully!')
            return redirect(url_for('main.dashboard'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred updating your profile.')
            print(f"Error updating profile: {e}")
            
    return render_template('edit_profile.html')
