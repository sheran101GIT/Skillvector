from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from ..models import Candidate, Job, ReviewEmail, db
from datetime import datetime
import os

bp = Blueprint('reviews', __name__, url_prefix='/reviews')

@bp.route('/')
@login_required
def index():
    # Fetch all candidates for current user's jobs
    candidates = Candidate.query.join(Job).filter(Job.recruiter_id == current_user.id).order_by(Candidate.created_at.desc()).all()
    
    # Calculate Stats
    total   = len(candidates)
    sent    = sum(1 for c in candidates if c.review_status == 'sent')
    pending = sum(1 for c in candidates if c.review_status == 'pending')
    active  = total

    # Filter logic if query param exists (e.g. ?status=pending)
    filter_status = request.args.get('status')
    if filter_status:
        display_candidates = [c for c in candidates if c.review_status == filter_status]
    else:
        display_candidates = candidates

    return render_template('reviews.html',
                           candidates=display_candidates,
                           all_candidates=candidates,
                           stats={'total': total, 'sent': sent, 'pending': pending, 'active': active},
                           current_filter=filter_status)


@bp.route('/mark-copied/<int:email_id>', methods=['POST'])
@login_required
def mark_copied(email_id):
    """Mark a generated review email as copied and update candidate review_status."""
    review_email = ReviewEmail.query.get_or_404(email_id)
    candidate    = Candidate.query.get_or_404(review_email.candidate_id)

    # Auth check
    if candidate.job and candidate.job.recruiter_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    review_email.status     = 'copied'
    candidate.review_status = 'sent'
    db.session.commit()

    return jsonify({'message': 'Marked as copied', 'candidate_id': candidate.id})


@bp.route('/send-email/<int:email_id>', methods=['POST'])
@login_required
def send_email(email_id):
    """Send the generated review email to the candidate via SMTP."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    review_email = ReviewEmail.query.get_or_404(email_id)
    candidate    = Candidate.query.get_or_404(review_email.candidate_id)

    # Auth check
    if candidate.job and candidate.job.recruiter_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    # Validate candidate has an email
    if not candidate.email:
        return jsonify({'error': 'Candidate has no email address on file.'}), 400

    # SMTP Credentials from environment
    smtp_host     = os.environ.get('MAIL_SMTP_HOST', 'smtp.gmail.com')
    smtp_port     = int(os.environ.get('MAIL_SMTP_PORT', 587))
    mail_sender   = os.environ.get('MAIL_SENDER')
    mail_password = os.environ.get('MAIL_PASSWORD')

    if not mail_sender or not mail_password:
        return jsonify({
            'error': 'Email sending not configured. Please set MAIL_SENDER and MAIL_PASSWORD environment variables.'
        }), 500

    # Build MIME email
    msg = MIMEMultipart('alternative')
    msg['Subject'] = review_email.email_subject or 'Candidate Review'
    msg['From']    = mail_sender
    msg['To']      = candidate.email

    # Plain-text body
    body_text = review_email.email_body or ''
    msg.attach(MIMEText(body_text, 'plain'))

    # HTML version with basic formatting
    html_body = '<html><body><pre style="font-family:sans-serif;white-space:pre-wrap;">' + \
                body_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;') + \
                '</pre></body></html>'
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(mail_sender, mail_password)
            server.sendmail(mail_sender, candidate.email, msg.as_string())

        # Mark as sent in DB
        review_email.status     = 'sent'
        candidate.review_status = 'sent'
        db.session.commit()

        print(f"[SendEmail] Sent review email #{email_id} to {candidate.email}", flush=True)
        return jsonify({'message': f'Email sent successfully to {candidate.email}'}), 200

    except smtplib.SMTPAuthenticationError as e:
        msg_detail = (
            'Gmail App Password required. Go to myaccount.google.com/apppasswords, '
            'generate a 16-character App Password, and update MAIL_PASSWORD in your .env file. '
            f'(SMTP error: {e.smtp_code} {e.smtp_error.decode() if isinstance(e.smtp_error, bytes) else e.smtp_error})'
        )
        print(f"[SendEmail] SMTP auth failed: {msg_detail}", flush=True)
        return jsonify({'error': msg_detail}), 500
    except smtplib.SMTPConnectError as e:
        print(f"[SendEmail] SMTP connect failed: {e}", flush=True)
        return jsonify({'error': f'Cannot connect to SMTP server {smtp_host}:{smtp_port}. Check MAIL_SMTP_HOST and MAIL_SMTP_PORT.'}), 500
    except smtplib.SMTPRecipientsRefused as e:
        print(f"[SendEmail] Recipient refused: {e}", flush=True)
        return jsonify({'error': f'Recipient email address was refused: {candidate.email}'}), 500
    except Exception as e:
        print(f"[SendEmail] Failed: {e}", flush=True)
        return jsonify({'error': f'Failed to send email: {str(e)}'}), 500


@bp.route('/send/<int:candidate_id>', methods=['POST'])
@login_required
def send_review(candidate_id):
    """Legacy route — marks candidate review_status as sent."""
    candidate = Candidate.query.get_or_404(candidate_id)
    if candidate.job and candidate.job.recruiter_id != current_user.id:
        return redirect(url_for('main.dashboard'))

    candidate.review_status = 'sent'
    db.session.commit()

    flash(f"Review for {candidate.name} marked as sent.", "success")
    return redirect(url_for('reviews.index'))


@bp.route('/send-all', methods=['POST'])
@login_required
def send_all_pending():
    candidates = Candidate.query.join(Job).filter(
        Job.recruiter_id == current_user.id,
        Candidate.review_status == 'pending'
    ).all()

    count = len(candidates)
    for c in candidates:
        c.review_status = 'sent'

    db.session.commit()
    flash(f"Marked {count} pending reviews as sent.", "success")
    return redirect(url_for('reviews.index'))
