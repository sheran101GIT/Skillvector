"""
Google Forms API Service
========================
Handles all interactions with the Google Forms API and Google Drive API.

Setup:
  1. Create a Google Cloud project.
  2. Enable "Google Forms API" and "Google Drive API".
  3. Create a Service Account, download the JSON key.
  4. Set GOOGLE_SERVICE_ACCOUNT_JSON env var to the full JSON string.

The service account does NOT need to be added to the form as a collaborator —
it only needs the form to be shared with it OR the form responses API to be
accessible (public forms work automatically).
"""

import os
import re
import io
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Candidate field names we map to
# ---------------------------------------------------------------------------
CANDIDATE_FIELDS = [
    'name', 'email', 'phone', 'resume_text',
    'resume_file',   # Drive file URL — we'll download and extract
    'linkedin_url', 'github_url', 'ignore'
]

# Keywords used for fuzzy auto-detection of field mapping
FIELD_KEYWORDS = {
    'name':         ['name', 'full name', 'candidate name', 'applicant name', 'your name'],
    'email':        ['email', 'e-mail', 'mail', 'email address'],
    'phone':        ['phone', 'mobile', 'contact number', 'telephone', 'cell'],
    'resume_text':  ['resume', 'cv', 'cover letter', 'paste resume', 'resume text', 'bio', 'summary'],
    'resume_file':  ['upload resume', 'resume file', 'attach', 'upload cv', 'file upload'],
    'linkedin_url': ['linkedin', 'linked in', 'linkedin url', 'linkedin profile'],
    'github_url':   ['github', 'git hub', 'github url', 'github profile'],
}


def _build_service(api_name: str, version: str, scopes: list):
    """Build a Google API service client using service account credentials."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    sa_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not sa_json:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON env var is not set. "
            "Please add your service account JSON as an environment variable."
        )

    try:
        sa_info = json.loads(sa_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON — not valid JSON: {e}")

    credentials = service_account.Credentials.from_service_account_info(
        sa_info, scopes=scopes
    )
    return build(api_name, version, credentials=credentials, cache_discovery=False)


def extract_form_id_from_url(url: str) -> str | None:
    """
    Extract the Google Form ID from a variety of URL formats:
      - https://docs.google.com/forms/d/<ID>/edit
      - https://docs.google.com/forms/d/e/<ID>/viewform
      - https://forms.gle/<shortcode>  (not supported — needs redirect)
    """
    # Standard Google Forms URL (supports /d/ or /d/e/)
    match = re.search(r'/forms/d/(?:e/)?([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    # If they paste the form ID directly
    if re.match(r'^[a-zA-Z0-9_-]{20,}$', url.strip()):
        return url.strip()
    return None


def auto_detect_field_mapping(questions: list[dict]) -> dict:
    """
    Given a list of question dicts (id, title), return a mapping:
    { question_id: candidate_field_name }

    Uses keyword matching against FIELD_KEYWORDS. Unmatched → 'ignore'.
    """
    mapping = {}
    for q in questions:
        q_id = q['id']
        title_lower = q['title'].lower().strip()
        matched_field = 'ignore'
        for field, keywords in FIELD_KEYWORDS.items():
            if any(kw in title_lower for kw in keywords):
                matched_field = field
                break
        mapping[q_id] = matched_field
    return mapping


# ---------------------------------------------------------------------------
# Main service class
# ---------------------------------------------------------------------------

class GoogleFormsService:

    FORMS_SCOPES = [
        'https://www.googleapis.com/auth/forms.responses.readonly',
        'https://www.googleapis.com/auth/forms.body.readonly',
        'https://www.googleapis.com/auth/drive.readonly',
    ]

    def __init__(self):
        self._forms = None
        self._drive = None

    @property
    def forms(self):
        if self._forms is None:
            self._forms = _build_service('forms', 'v1', self.FORMS_SCOPES)
        return self._forms

    @property
    def drive(self):
        if self._drive is None:
            self._drive = _build_service('drive', 'v3', self.FORMS_SCOPES)
        return self._drive

    # ------------------------------------------------------------------
    # Form metadata
    # ------------------------------------------------------------------

    def get_form_metadata(self, form_id: str) -> dict:
        """
        Returns:
          {
            'title': str,
            'questions': [{'id': str, 'title': str, 'type': str}, ...]
          }
        """
        try:
            form = self.forms.forms().get(formId=form_id).execute()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch form metadata: {e}")

        title = form.get('info', {}).get('title', 'Untitled Form')
        questions = []

        for item in form.get('items', []):
            question = item.get('questionItem', {}).get('question', {})
            if not question:
                continue
            q_id = question.get('questionId', item.get('itemId', ''))
            q_title = item.get('title', '')
            q_type = list(question.keys())[-1] if question else 'unknown'
            questions.append({
                'id': q_id,
                'title': q_title,
                'type': q_type,
            })

        return {'title': title, 'questions': questions}

    # ------------------------------------------------------------------
    # Fetch responses
    # ------------------------------------------------------------------

    def get_form_responses(self, form_id: str, after_response_id: str = None) -> list[dict]:
        """
        Fetch all responses for a form, optionally only those after
        `after_response_id` (used as a deduplication cursor).

        Returns a list of raw Google Forms response dicts.
        """
        try:
            result = self.forms.forms().responses().list(formId=form_id).execute()
        except Exception as e:
            raise RuntimeError(f"Failed to fetch form responses: {e}")

        responses = result.get('responses', [])

        if not after_response_id:
            return responses

        # Filter: only responses after the last seen one
        # Responses are ordered by submit time (oldest first)
        seen = False
        new_responses = []
        for r in responses:
            if seen:
                new_responses.append(r)
            if r.get('responseId') == after_response_id:
                seen = True

        # If we never found the cursor, return all (safety fallback)
        return new_responses if seen else responses

    # ------------------------------------------------------------------
    # Map response → candidate dict
    # ------------------------------------------------------------------

    def extract_candidate_from_response(
        self,
        response: dict,
        field_mapping: dict,
        questions: list[dict]
    ) -> dict:
        """
        Maps a Google Forms response to a candidate data dict using
        field_mapping {question_id: candidate_field}.

        Returns a dict with keys: name, email, phone, resume_text,
        resume_file_url, linkedin_url, github_url
        """
        # Build a lookup: question_id → answer text
        answers = response.get('answers', {})
        candidate = {
            'name': None,
            'email': None,
            'phone': None,
            'resume_text': None,
            'resume_file_url': None,
            'linkedin_url': None,
            'github_url': None,
        }

        # Build question title lookup
        q_title_map = {q['id']: q['title'] for q in questions}

        for q_id, answer_obj in answers.items():
            mapped_field = field_mapping.get(q_id, 'ignore')
            if mapped_field == 'ignore':
                continue

            # Extract text value
            text_answers = answer_obj.get('textAnswers', {}).get('answers', [])
            file_answers = answer_obj.get('fileUploadAnswers', {}).get('answers', [])

            if mapped_field == 'resume_file' and file_answers:
                # File upload — get the Drive file ID
                file_id = file_answers[0].get('fileId')
                if file_id:
                    candidate['resume_file_url'] = f"https://drive.google.com/open?id={file_id}"
                    # Store file_id separately for download
                    candidate['_resume_drive_file_id'] = file_id
            elif text_answers:
                value = text_answers[0].get('value', '').strip()
                if mapped_field in candidate:
                    candidate[mapped_field] = value

        return candidate

    # ------------------------------------------------------------------
    # Download resume from Drive
    # ------------------------------------------------------------------

    def download_drive_file(self, file_id: str) -> tuple[bytes, str]:
        """
        Download a file from Google Drive by file ID.
        Returns (file_bytes, mime_type).
        """
        from googleapiclient.http import MediaIoBaseDownload

        try:
            # Get file metadata to determine MIME type
            meta = self.drive.files().get(
                fileId=file_id, fields='name,mimeType'
            ).execute()
            mime_type = meta.get('mimeType', '')
            filename = meta.get('name', '')

            # Download
            request = self.drive.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

            buf.seek(0)
            return buf.read(), mime_type, filename

        except Exception as e:
            raise RuntimeError(f"Failed to download Drive file {file_id}: {e}")

    # ------------------------------------------------------------------
    # Full sync: process all new responses for a connection
    # ------------------------------------------------------------------

    def sync_connection(self, connection, app_context) -> dict:
        """
        Full sync for a GoogleFormConnection object.
        Must be called within an app context.

        Returns {'imported': int, 'errors': list[str]}
        """
        from .models import Candidate, db
        from .services import process_candidate_background

        imported = 0
        errors = []

        try:
            # 1. Fetch form metadata (for question titles)
            meta = self.get_form_metadata(connection.form_id)
            questions = meta['questions']

            field_mapping = connection.field_mapping or {}

            # 2. Fetch new responses
            responses = self.get_form_responses(
                connection.form_id,
                after_response_id=connection.last_response_id
            )

            logger.info(f"[GoogleForms] {len(responses)} new response(s) for form {connection.form_id}")

            last_response_id = connection.last_response_id

            for response in responses:
                response_id = response.get('responseId')
                try:
                    # 3. Extract candidate data
                    cdata = self.extract_candidate_from_response(
                        response, field_mapping, questions
                    )

                    # 4. Build resume text — try file first, fallback to text
                    resume_text = cdata.get('resume_text') or ''

                    drive_file_id = cdata.get('_resume_drive_file_id')
                    if drive_file_id:
                        try:
                            file_bytes, mime_type, filename = self.download_drive_file(drive_file_id)
                            resume_text = self._extract_text_from_bytes(
                                file_bytes, mime_type, filename
                            )
                        except Exception as e:
                            logger.warning(f"[GoogleForms] Could not download resume file: {e}")
                            if not resume_text:
                                resume_text = f"Resume file uploaded (Drive ID: {drive_file_id})"

                    if not resume_text:
                        resume_text = "No resume text provided."

                    # 5. Create candidate
                    name = cdata.get('name') or f"Applicant ({response_id[:8]})"
                    candidate = Candidate(
                        name=name,
                        email=cdata.get('email'),
                        phone=cdata.get('phone'),
                        linkedin_url=cdata.get('linkedin_url'),
                        github_url=cdata.get('github_url'),
                        resume_text=resume_text,
                        source='Google Forms',
                        processing_status='pending',
                        job_id=connection.job_id,
                    )
                    db.session.add(candidate)
                    db.session.flush()

                    # 6. Trigger AI pipeline
                    from . import executor
                    executor.submit(process_candidate_background, candidate.id, connection.job_id)

                    last_response_id = response_id
                    imported += 1

                except Exception as e:
                    logger.error(f"[GoogleForms] Error processing response {response_id}: {e}")
                    errors.append(str(e))

            # 7. Update connection cursor and stats
            connection.last_response_id = last_response_id
            connection.last_sync = datetime.utcnow()
            connection.total_synced = (connection.total_synced or 0) + imported
            connection.sync_status = 'active' if not errors else 'error'
            connection.last_error = errors[-1] if errors else None
            db.session.commit()

        except Exception as e:
            logger.error(f"[GoogleForms] Sync failed for connection {connection.id}: {e}")
            connection.sync_status = 'error'
            connection.last_error = str(e)
            db.session.commit()
            errors.append(str(e))

        return {'imported': imported, 'errors': errors}

    # ------------------------------------------------------------------
    # Text extraction from downloaded bytes
    # ------------------------------------------------------------------

    def _extract_text_from_bytes(self, file_bytes: bytes, mime_type: str, filename: str) -> str:
        """Extract text from PDF or DOCX bytes."""
        import io as _io

        filename_lower = (filename or '').lower()

        if 'pdf' in mime_type or filename_lower.endswith('.pdf'):
            try:
                import pdfplumber
                with pdfplumber.open(_io.BytesIO(file_bytes)) as pdf:
                    return '\n'.join(
                        page.extract_text() or '' for page in pdf.pages
                    ).strip()
            except Exception as e:
                logger.warning(f"[GoogleForms] PDF extraction failed: {e}")
                return ''

        elif 'word' in mime_type or filename_lower.endswith('.docx'):
            try:
                import docx
                doc = docx.Document(_io.BytesIO(file_bytes))
                return '\n'.join(p.text for p in doc.paragraphs).strip()
            except Exception as e:
                logger.warning(f"[GoogleForms] DOCX extraction failed: {e}")
                return ''

        # Plain text fallback
        try:
            return file_bytes.decode('utf-8', errors='ignore').strip()
        except Exception:
            return ''


# ---------------------------------------------------------------------------
# Module-level singleton helper
# ---------------------------------------------------------------------------

_service_instance = None

def get_google_forms_service() -> GoogleFormsService:
    """Returns a cached GoogleFormsService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = GoogleFormsService()
    return _service_instance
