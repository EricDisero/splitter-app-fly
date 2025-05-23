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
    """Validate email access against the GHL API and update database"""
    try:
        logger.info(f"Email before cleaning: {email}, type: {type(email)}")
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

        # Step 2: Fetch the contacts list (v1)
        list_url = f"https://rest.gohighlevel.com/v1/contacts/?email={email}"
        list_res = requests.get(
            list_url,
            headers={'Authorization': f'Bearer {API_KEY}'},
            timeout=10
        )
        
        if not list_res.ok:
            logger.error(f'❌ v1 contacts list error: {list_res.status_code} {list_res.text}')
            return False

        list_data = list_res.json()
        contacts = list_data.get('contacts', [])
        logger.info(f"Contacts found: {len(contacts)}")

        # Step 3: Exact-match filter
        if not isinstance(contacts, list) or len(contacts) == 0:
            logger.info(f'❌ No contacts found at all for: {email}')
            return False

        # Find exact match
        exact = None
        for contact in contacts:
            if contact is None:
                logger.warning("Found None contact in contacts list")
                continue
                
            logger.debug(f"Contact data: {contact}")
            contact_email = contact.get('email', '')
            if contact_email is None:
                logger.warning(f"Contact has None email: {contact}")
                continue
                
            contact_email = contact_email.lower().strip()
            if contact_email == email:
                exact = contact
                break

        if not exact:
            logger.info(f'❌ No EXACT email match for: {email}')
            return False

        logger.info(f'✓ Found EXACT contact match: {exact.get("email")} (ID: {exact.get("id")})')
        contact_id = exact.get("id")

        # Step 4: Gather tags from the contact
        tags = []
        exact_tags = exact.get('tags')
        logger.info(f"Tags data type: {type(exact_tags)}, value: {exact_tags}")
        
        if isinstance(exact_tags, list):
            tags = exact_tags
        elif isinstance(exact_tags, str):
            tags = exact_tags.split(',')
            tags = [t.strip() for t in tags]
        
        # Log each tag for debugging
        for i, tag in enumerate(tags):
            logger.info(f"Tag {i}: {tag}, type: {type(tag)}")
        
        logger.info(f'Tags for {email} → {tags}')

        # Create a helper function to check for tags
        def has_tag(tag_substring):
            return any(tag_substring.lower() in tag.lower() for tag in tags if isinstance(tag, str))

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
            
        elif has_tag(YEARLY_TAG):
            access_type = 'yearly'
            has_access = True
            monthly_limit = 0  # unlimited
            
        elif has_tag(MONTHLY_TAG):
            access_type = 'monthly'
            has_access = True
            monthly_limit = DEFAULT_MONTHLY_LIMIT
            
        elif has_tag(DEMO_TAG):
            access_type = 'demo'
            has_access = True
            monthly_limit = 0  # demo uses total limit instead
        
        # Try to get or create user account in our database
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
            
        logger.info(f'Decision for {email}: {"✅ GRANTED" if has_access else "❌ DENIED"} (access_type: {access_type})')
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
                
                # If it's been more than 30 minutes since last validation, revalidate with GHL
                if timezone.now() > user.last_validated_at + timedelta(minutes=30):
                    logger.info(f"Revalidating access with GHL for {email}")
                    if not check_ghl_access(email):
                        logger.warning(f"GHL access revoked for {email}")
                        del request.session[ACCESS_SESSION_KEY]
                        return False
                
                # Check if user still has active access in our database
                if not user.has_active_access:
                    logger.warning(f"User no longer has active access: {email}")
                    del request.session[ACCESS_SESSION_KEY]
                    return False
                    
                logger.info(f"Valid access found for {email} (type: {user.access_type})")
                return True
                
            except UserAccount.DoesNotExist:
                logger.warning(f"User account not found in database: {email}")
                # Try to revalidate with GHL
                if check_ghl_access(email):
                    logger.info(f"Revalidated access with GHL for {email}")
                    return True
                else:
                    del request.session[ACCESS_SESSION_KEY]
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