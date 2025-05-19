import os
from django.conf import settings
import requests
import json
import logging
import hashlib
from datetime import datetime, timedelta

logger = logging.getLogger("general_logger")

# Constants for session management
ACCESS_SESSION_KEY = 'validated_access'
ACCESS_EXPIRY_HOURS = 24

def get_email_hash(email):
    """Create a secure hash of the email"""
    salt = settings.SECRET_KEY[:16]
    return hashlib.sha256((email + salt).encode()).hexdigest()

def check_ghl_access(email):
    """Validate email access against the GHL API - following exact Vercel pattern"""
    # Clean and validate email (exact same as Vercel)
    email = email.lower().strip()
    if not email:
        logger.error('Missing email parameter')
        return False
    
    # Check for API key
    API_KEY = settings.GHL_API_KEY
    if not API_KEY:
        logger.error('❌ GHL_API_KEY not configured')
        return False

    logger.info(f'Checking access for email: {email}')

    try:
        # Step 2: Fetch the contacts list (v1) - EXACT same endpoint as Vercel
        list_url = f"https://rest.gohighlevel.com/v1/contacts/?email={email}"
        list_res = requests.get(
            list_url,
            headers={'Authorization': f'Bearer {API_KEY}'},
            timeout=10
        )
        
        if not list_res.ok:
            logger.error(f'❌ v1 contacts list error: {list_res.status_code} {list_res.status_text}')
            return False

        list_data = list_res.json()
        contacts = list_data.get('contacts', [])

        # Step 3: Exact-match filter (SAME logic as Vercel)
        if not isinstance(contacts, list) or len(contacts) == 0:
            logger.info(f'❌ No contacts found at all for: {email}')
            return False

        # Find exact match
        exact = None
        for contact in contacts:
            contact_email = contact.get('email', '').lower().strip()
            if contact_email == email:
                exact = contact
                break

        if not exact:
            logger.info(f'❌ No EXACT email match for: {email}')
            return False

        logger.info(f'✓ Found EXACT contact match: {exact.get("email")} (ID: {exact.get("id")})')

        # Step 4: Gather tags strictly from that contact (SAME as Vercel)
        tags = []
        exact_tags = exact.get('tags')
        if isinstance(exact_tags, list):
            tags = exact_tags
        elif isinstance(exact_tags, str):
            tags = exact_tags.split(',')
            tags = [t.strip() for t in tags]
        
        logger.info(f'Tags for {email} → {tags}')

        # Step 5: Check for access tag (SAME logic as Vercel gate)
        required_tag = settings.GHL_ACCESS_TAG.lower()
        has_access = any(required_tag in tag.lower() for tag in tags)

        reason = 'has_proper_tag' if has_access else 'missing_splitter_access_tag'
        logger.info(f'Decision for {email}: {"✅ GRANTED" if has_access else "❌ DENIED"} ({reason})')

        return has_access

    except Exception as err:
        logger.error(f'🔥 Error in check_ghl_access: {err}')
        return False

def store_access_in_session(request, email):
    """Store the validated email in the session"""
    if hasattr(request, 'session'):
        email_hash = get_email_hash(email)
        request.session[ACCESS_SESSION_KEY] = {
            'hash': email_hash,
            'email': email,
            'expires': (datetime.now() + timedelta(hours=ACCESS_EXPIRY_HOURS)).isoformat()
        }
        request.session.set_expiry(ACCESS_EXPIRY_HOURS * 3600)
        logger.info("Access stored in session")
        return True
    else:
        logger.warning("Session not available for access storage")
        return False

def is_access_valid(request):
    """Check if a valid access exists in the session"""
    if hasattr(request, 'session') and ACCESS_SESSION_KEY in request.session:
        access_data = request.session[ACCESS_SESSION_KEY]
        
        try:
            expiry = datetime.fromisoformat(access_data['expires'])
            if datetime.now() < expiry:
                logger.info("Valid access found in session")
                return True
            else:
                logger.info("Access in session has expired")
                del request.session[ACCESS_SESSION_KEY]
        except (ValueError, KeyError) as e:
            logger.error(f"Error parsing access data from session: {str(e)}")
            del request.session[ACCESS_SESSION_KEY]
    
    logger.info("No valid access found in session")
    return False

def clear_access(request):
    """Clear access data from session"""
    if hasattr(request, 'session') and ACCESS_SESSION_KEY in request.session:
        del request.session[ACCESS_SESSION_KEY]
    logger.info("Access data cleared")

# Keep these for backward compatibility - just alias the new functions
check_key = check_ghl_access
is_license_valid = is_access_valid
store_license_in_session = store_access_in_session
clear_license = clear_access