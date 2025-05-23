import os
from django.conf import settings
import requests
import json
import logging
import hashlib
from datetime import datetime, timedelta
from django.utils import timezone
from .models import UserAccount, SplitUsage
from django.db import ProgrammingError, OperationalError

logger = logging.getLogger("general_logger")

# Constants for session management
ACCESS_SESSION_KEY = 'validated_access'
ACCESS_EXPIRY_HOURS = 24

# Constants for access tags
DEMO_TAG = "splitter demo"
MONTHLY_TAG = "splitter access"
YEARLY_TAG = "splitter yearly"
LIFETIME_TAG = "splitter lifetime"

# Constants for file limits
MAX_FILE_DURATION_SECONDS = 600  # 10 minutes maximum

# Default usage limits
DEFAULT_DEMO_LIMIT = 3
DEFAULT_MONTHLY_LIMIT = 10

def get_email_hash(email):
    """Create a secure hash of the email"""
    salt = settings.SECRET_KEY[:16]
    return hashlib.sha256((email + salt).encode()).hexdigest()

def check_ghl_access(email):
    """Validate email access against the GHL API and update database
    Returns: (has_access, access_type, message, email_found)
    """
    try:
        logger.info(f"Email before cleaning: {email}, type: {type(email)}")
        email = email.lower().strip()
        if not email:
            logger.error('Missing email parameter')
            return False, 'none', 'Missing email parameter', False
        
        # Check for API key
        API_KEY = settings.GHL_API_KEY
        if not API_KEY:
            logger.error('❌ GHL_API_KEY not configured')
            return False, 'none', 'API configuration error', False

        logger.info(f'Checking access for email: {email}')

        # Step 1: Check if we already have this user in our database with recent validation
        try:
            email_hash = get_email_hash(email)
            user = UserAccount.objects.get(email_hash=email_hash)
            
            # Always re-validate tags to ensure immediate access level changes
            # but we'll update the database with fresh tag data each time
            logger.info(f"Found existing user {email}, re-validating tags for immediate access changes...")
                
        except UserAccount.DoesNotExist:
            pass  # User not in database, need to fetch from GHL
        
        # Step 2: Try multiple search approaches for instant results
        session = requests.Session()
        session.headers.update({'Authorization': f'Bearer {API_KEY}'})
        
        exact = None
        
        try:
            # Try exact email search with query parameter (this is fast and effective)
            logger.info(f"Searching for email: {email}")
            search_url = f"https://rest.gohighlevel.com/v1/contacts/?query={email}&limit=100"
            search_res = session.get(search_url, timeout=10)
            
            if search_res.ok:
                search_data = search_res.json()
                contacts = search_data.get('contacts', [])
                logger.info(f"Query search returned {len(contacts)} contacts")
                
                # Look for exact match
                for contact in contacts:
                    if contact and contact.get('email', '').lower().strip() == email:
                        exact = contact
                        logger.info(f'✓ FOUND via query search: {contact.get("email")}')
                        break
                    
        finally:
            session.close()

        if not exact:
            logger.info(f'❌ No contact found for email: {email} after trying all search methods')
            return False, 'none', f'Email {email} not found in our system. Please email hello@mypulseacademy.com to get access.', False

        contact_id = exact.get("id")

        # Step 3: Process tags from the contact
        tags = []
        exact_tags = exact.get('tags')
        logger.info(f"Tags data type: {type(exact_tags)}, value: {exact_tags}")
        
        if isinstance(exact_tags, list):
            # Filter out None values and ensure strings
            tags = [str(tag).strip() for tag in exact_tags if tag is not None and str(tag).strip()]
        elif isinstance(exact_tags, str):
            tags = exact_tags.split(',')
            tags = [t.strip() for t in tags if t.strip()]
        
        # Log each tag for debugging
        for i, tag in enumerate(tags):
            logger.info(f"Tag {i}: '{tag}', type: {type(tag)}")
        
        logger.info(f'All tags for {email}: {tags}')

        # Step 4: Check for access tags (case insensitive)
        def has_tag(tag_substring):
            if not tags:
                return False
            return any(
                tag_substring.lower() in str(tag).lower() 
                for tag in tags 
                if tag is not None and str(tag).strip()
            )

        # Determine access type based on tags (in order of priority)
        access_type = 'none'
        has_access = False
        monthly_limit = 0
        demo_limit = DEFAULT_DEMO_LIMIT
        
        # Process tags in order of priority (most premium first)
        if has_tag(LIFETIME_TAG):
            access_type = 'lifetime'
            has_access = True
            monthly_limit = 0  # unlimited
            logger.info(f"✅ LIFETIME access granted for {email}")
            
        elif has_tag(YEARLY_TAG):
            access_type = 'yearly'
            has_access = True
            monthly_limit = 0  # unlimited
            logger.info(f"✅ YEARLY access granted for {email}")
            
        elif has_tag(MONTHLY_TAG):
            access_type = 'monthly'
            has_access = True
            monthly_limit = DEFAULT_MONTHLY_LIMIT
            logger.info(f"✅ MONTHLY access granted for {email}")
            
        elif has_tag(DEMO_TAG):
            access_type = 'demo'
            has_access = True
            monthly_limit = 0  # demo uses total limit instead
            logger.info(f"✅ DEMO access granted for {email}")
        else:
            logger.info(f"❌ No valid access tags found for {email}. Available tags: {tags}")
        
        # Step 5: Update user account in our database
        try:
            email_hash = get_email_hash(email)
            
            try:
                user, created = UserAccount.objects.update_or_create(
                    email_hash=email_hash,
                    defaults={
                        'email': email,
                        'ghl_contact_id': contact_id,
                        'access_type': access_type,
                        'has_active_access': has_access,
                        'monthly_limit': monthly_limit,
                        'demo_limit': demo_limit,
                        'current_tags': tags,
                        'last_validated_at': timezone.now()
                    }
                )
                logger.info(f"User account {'created' if created else 'updated'} in database")
            except (ProgrammingError, OperationalError) as e:
                # This happens when the table doesn't exist yet (migrations not applied)
                logger.warning(f"Database error when storing user account: {e}")
                # Continue with just GHL validation, don't let database issues prevent access
                pass
        except Exception as db_err:
            logger.error(f"Error updating user account in database: {db_err}")
            # Continue without storing in DB - we have GHL validation
        
        # Return detailed result
        if has_access:
            message = f"Access granted ({access_type})"
            logger.info(f'Final decision for {email}: ✅ GRANTED (access_type: {access_type})')
        else:
            message = f'Your email ({email}) was found in our system but you don\'t have access. Please email hello@mypulseacademy.com to get access.'
            logger.info(f'Final decision for {email}: ❌ DENIED (no valid tags)')
            
        return has_access, access_type, message, True  # email_found = True

    except Exception as err:
        logger.error(f'🔥 Error in check_ghl_access: {err}')
        return False, 'none', 'An error occurred while checking access', False

def fetch_access_contacts_from_ghl():
    """This function is no longer needed - kept for compatibility"""
    logger.warning("fetch_access_contacts_from_ghl() is deprecated")
    return []

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
    """Check if a valid access exists in the session and validate against database"""
    if hasattr(request, 'session') and ACCESS_SESSION_KEY in request.session:
        access_data = request.session[ACCESS_SESSION_KEY]
        
        try:
            email = access_data.get('email')
            email_hash = access_data.get('hash')
            
            # Double-check the hash
            if email and email_hash != get_email_hash(email):
                logger.warning(f"Email hash mismatch, possible tampering: {email}")
                del request.session[ACCESS_SESSION_KEY]
                return False
            
            # Check if the session is expired
            expiry = datetime.fromisoformat(access_data['expires'])
            if datetime.now() >= expiry:
                logger.info("Access in session has expired")
                del request.session[ACCESS_SESSION_KEY]
                return False
                
            # Validate against database (periodic re-validation to catch tag removals)
            try:
                user = UserAccount.objects.get(email_hash=email_hash)
                
                # Check if user still has active access by re-validating with GHL every time
                # This ensures immediate tag change detection while keeping email session alive
                logger.info(f"Re-validating current access level for {email}")
                has_access, access_type, message, email_found = check_ghl_access(email)
                
                if not email_found:
                    # Email was removed from GHL entirely - delete session
                    logger.warning(f"Email {email} no longer exists in GHL system")
                    del request.session[ACCESS_SESSION_KEY]
                    return False
                elif not has_access:
                    # Email exists but no access - keep session but deny access
                    logger.warning(f"Email {email} found but access denied: {message}")
                    return False
                
                # If validation passed, access is still valid
                logger.info(f"Access confirmed for {email}: {message}")
                return True
                
            except UserAccount.DoesNotExist:
                logger.warning(f"User account not found in database: {email}")
                # Try to revalidate with GHL
                has_access, access_type, message, email_found = check_ghl_access(email)
                if email_found and has_access:
                    logger.info(f"Revalidated access with GHL for {email}")
                    return True
                elif not email_found:
                    # Email not found in GHL - delete session
                    del request.session[ACCESS_SESSION_KEY]
                    return False
                else:
                    # Email found but no access - keep session but deny
                    return False
                
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

def get_current_user(request):
    """Get the current user from session information"""
    if hasattr(request, 'session') and ACCESS_SESSION_KEY in request.session:
        access_data = request.session[ACCESS_SESSION_KEY]
        email_hash = access_data.get('hash')
        
        try:
            return UserAccount.objects.get(email_hash=email_hash)
        except UserAccount.DoesNotExist:
            return None
    
    return None

def check_usage_limits(request):
    """
    Check if the user has reached their usage limits
    Returns: (can_use, message)
    """
    user = get_current_user(request)
    if not user:
        return False, "User not authenticated"
    
    # For demo accounts, check total usage
    if user.access_type == 'demo':
        total_usage = SplitUsage.objects.filter(user=user).count()
        if total_usage >= user.demo_limit:
            return False, f"You have used all {user.demo_limit} demo splits. Upgrade for more!"
            
    # For monthly accounts, check this month's usage
    elif user.access_type in ['monthly', 'yearly'] and user.monthly_limit > 0:
        now = timezone.now()
        monthly_usage = SplitUsage.objects.filter(
            user=user,
            year=now.year,
            month=now.month
        ).count()
        
        if monthly_usage >= user.monthly_limit:
            return False, f"You have used all {user.monthly_limit} splits for this month"
        
        remaining = user.monthly_limit - monthly_usage
        return True, f"You have {remaining} splits remaining this month"
    
    return True, ""

def validate_file_duration(audio_path):
    """Check if the audio file duration is within limits"""
    try:
        import librosa
        
        # Get the duration of the audio file
        duration = librosa.get_duration(path=audio_path)
        
        if duration > MAX_FILE_DURATION_SECONDS:
            return False, f"File duration exceeds the maximum allowed ({MAX_FILE_DURATION_SECONDS // 60} minutes)"
            
        return True, duration
        
    except Exception as e:
        logger.error(f"Error checking file duration: {e}")
        # If we can't determine duration, allow the file but log the error
        return True, 0

def record_usage(user, file_name, duration_seconds, job=None):
    """Record usage of the splitting service"""
    try:
        now = timezone.now()
        
        usage = SplitUsage(
            user=user,
            job=job,
            file_name=file_name,
            file_duration_seconds=duration_seconds,
            month=now.month,
            year=now.year
        )
        usage.save()
        
        return usage
    except Exception as e:
        logger.error(f"Error recording usage: {e}")
        return None

def get_user_usage_info(request):
    """Get the user's usage information for display"""
    info = {
        'has_user_info': False,
        'unlimited_usage': False,
        'monthly_reset': False,
        'usage_count': 0,
        'usage_limit': 0,
        'usage_remaining': 0,
    }
    
    try:
        if not hasattr(request, 'session') or ACCESS_SESSION_KEY not in request.session:
            return info
            
        access_data = request.session[ACCESS_SESSION_KEY]
        email = access_data.get('email')
        email_hash = access_data.get('hash')
        
        if not email or not email_hash:
            return info
            
        try:
            # Try to get user from database
            user = UserAccount.objects.get(email_hash=email_hash)
            
            info['has_user_info'] = True
            info['user_email'] = user.email
            info['access_type'] = user.access_type
            
            # Get usage info based on access type
            if user.access_type == 'demo':
                # For demo users, count all usage
                try:
                    total_usage = SplitUsage.objects.filter(user=user).count()
                    info['usage_count'] = total_usage
                    info['usage_limit'] = user.demo_limit
                    info['usage_remaining'] = max(0, user.demo_limit - total_usage)
                except (ProgrammingError, OperationalError):
                    # Table doesn't exist yet
                    info['usage_count'] = 0
                    info['usage_limit'] = user.demo_limit
                    info['usage_remaining'] = user.demo_limit
                    
            elif user.access_type in ['monthly', 'yearly'] and user.monthly_limit > 0:
                # For monthly users, count this month's usage
                try:
                    now = timezone.now()
                    monthly_usage = SplitUsage.objects.filter(
                        user=user, year=now.year, month=now.month).count()
                    info['usage_count'] = monthly_usage
                    info['usage_limit'] = user.monthly_limit
                    info['usage_remaining'] = max(0, user.monthly_limit - monthly_usage)
                    info['monthly_reset'] = True
                except (ProgrammingError, OperationalError):
                    # Table doesn't exist yet
                    info['usage_count'] = 0
                    info['usage_limit'] = user.monthly_limit
                    info['usage_remaining'] = user.monthly_limit
                    info['monthly_reset'] = True
            else:
                # Unlimited plans
                info['unlimited_usage'] = True
                
        except UserAccount.DoesNotExist:
            # User not in database yet - fallback to default demo limit
            info['has_user_info'] = True
            info['user_email'] = email
            info['access_type'] = 'unknown'
            
            # GHL tags will determine actual access, but we don't have that info here
            # Just show unlimited for now
            info['unlimited_usage'] = True
            
        except (ProgrammingError, OperationalError):
            # Tables don't exist yet - database migration issue
            logger.warning("Database tables don't exist yet for user info")
            # Return basic info only
            info['has_user_info'] = True
            info['user_email'] = email
            info['unlimited_usage'] = True  # Assume unlimited until DB is set up
            
    except Exception as e:
        logger.error(f"Error getting user usage info: {e}")
        
    return info

# Keep these for backward compatibility - just alias the new functions
check_key = check_ghl_access
is_license_valid = is_access_valid
store_license_in_session = store_access_in_session
clear_license = clear_access