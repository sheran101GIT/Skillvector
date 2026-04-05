from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..models import Job, db
from ..pipeline import generate_embedding

bp = Blueprint('jobs', __name__, url_prefix='/jobs')

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        try:
            # Get form data
            title = request.form.get('title', '').strip()
            department = request.form.get('department', '').strip()
            location = request.form.get('location', '').strip()
            experience_range = request.form.get('experience_range', '').strip()
            description = request.form.get('description', '').strip()
            required_skills_str = request.form.get('required_skills', '').strip()
            
            # Validate required fields
            if not title:
                flash('Job title is required', 'error')
                return redirect(url_for('uploads.index'))
            
            if not description:
                flash('Job description is required', 'error')
                return redirect(url_for('uploads.index'))
            
            # Parse skills
            required_skills = []
            if required_skills_str:
                required_skills = [s.strip() for s in required_skills_str.split(',') if s.strip()]
            
            # Generate embedding for the job description
            try:
                embedding = generate_embedding(description)
            except Exception as e:
                print(f"Error generating embedding: {e}")
                # Continue without embedding if generation fails
                embedding = None
            
            # Create job object
            job = Job(
                title=title, 
                department=department if department else None,
                location=location if location else None,
                experience_range=experience_range if experience_range else None,
                description=description, 
                required_skills=required_skills if required_skills else None,
                embedding=embedding, 
                recruiter_id=current_user.id,
                is_active=True
            )
            
            # Save to database
            db.session.add(job)
            db.session.commit()
            
            flash(f'Job "{title}" created successfully!', 'success')
            print(f"Successfully created job: {title} (ID: {job.id})")
            return redirect(url_for('uploads.index'))
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating job: {str(e)}")
            flash(f'Error creating job: {str(e)}', 'error')
            return redirect(url_for('uploads.index'))
        
    return render_template('job_form.html')

@bp.route('/<int:job_id>')
@login_required
def view(job_id):
    job = Job.query.get_or_404(job_id)
    if job.recruiter_id != current_user.id:
        flash('Unauthorized access')
        return redirect(url_for('main.dashboard'))
        
    # Sort candidates by analysis score
    # We need to join with Analysis
    candidates_with_analysis = []
    for candidate in job.candidates:
        analysis = next((a for a in candidate.analyses if a.job_id == job.id), None)
        score = analysis.final_score if analysis else 0
        candidates_with_analysis.append((candidate, score))
        
    candidates_with_analysis.sort(key=lambda x: x[1], reverse=True)
    
    return render_template('job_view.html', job=job, candidates_with_analysis=candidates_with_analysis)
@bp.route('/<int:job_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(job_id):
    job = Job.query.get_or_404(job_id)
    if job.recruiter_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('uploads.index'))

    if request.method == 'POST':
        job.title = request.form.get('title', job.title)
        job.department = request.form.get('department')
        job.location = request.form.get('location')
        job.experience_range = request.form.get('experience_range')
        job.description = request.form.get('description', job.description)
        
        required_skills_str = request.form.get('required_skills')
        if required_skills_str:
            job.required_skills = [s.strip() for s in required_skills_str.split(',') if s.strip()]
            
        try:
            # Re-embed if description changed
            job.embedding = generate_embedding(job.description)
            db.session.commit()
            flash('Job updated successfully', 'success')
            return redirect(url_for('uploads.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating job: {str(e)}', 'error')
            
    return render_template('job_edit.html', job=job) # Or reuse job_form with prepopulated data

@bp.route('/<int:job_id>/delete', methods=['POST'])
@login_required
def delete(job_id):
    job = Job.query.get_or_404(job_id)
    if job.recruiter_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('uploads.index'))
        
    try:
        # Delete related records or handle cascade?
        # For now, we'll just soft delete if foreign keys prevent hard delete, but user asked for "delete" features
        # Assuming DB handles validation, or we manually check candidates
        db.session.delete(job)
        db.session.commit()
        flash('Job deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        # Fallback to soft delete/deactivate if hard delete fails due to dependencies
        job.is_active = False
        db.session.commit()
        flash('Could not hard delete job due to dependencies. Job deactivated instead.', 'warning')
        
    return redirect(url_for('uploads.index'))

@bp.route('/templates/create', methods=['POST'])
@login_required
def create_template():
    from ..models import JobTemplate
    title = request.form.get('template_title')
    job_id = request.form.get('source_job_id')
    
    if not title:
        flash('Template title is required', 'error')
        return redirect(url_for('uploads.index'))
        
    if job_id:
        # Create from existing job
        job = Job.query.get(job_id)
        if job and job.recruiter_id == current_user.id:
            template = JobTemplate(
                title=title,
                job_title=job.title,
                description=job.description,
                required_skills=job.required_skills,
                department=job.department,
                experience_range=job.experience_range,
                created_by=current_user.id
            )
        else:
             flash('Invalid source job', 'error')
             return redirect(url_for('uploads.index'))
    else:
        # Create from scratch (not implemented in UI yet)
        pass 
        
    db.session.add(template)
    db.session.commit()
    flash(f'Template "{title}" created', 'success')
    return redirect(url_for('uploads.index'))

@bp.route('/templates/<int:template_id>/use')
@login_required
def use_template(template_id):
    from ..models import JobTemplate
    template = JobTemplate.query.get_or_404(template_id)
    # Return JSON for frontend to populate form
    return {
        'title': template.job_title,
        'description': template.description,
        'department': template.department,
        'location': '', # Templates usually don't have location
        'experience_range': template.experience_range,
        'required_skills': ', '.join(template.required_skills) if template.required_skills else ''
    }

@bp.route('/<int:job_id>/toggle_status', methods=['POST'])
@login_required
def toggle_status(job_id):
    job = Job.query.get_or_404(job_id)
    if job.recruiter_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('uploads.index'))
        
    job.is_active = not job.is_active
    db.session.commit()
    status = "Active" if job.is_active else "Inactive"
    flash(f'Job status changed to {status}', 'success')
    return redirect(url_for('uploads.index'))
