import os
from django.conf import settings
import requests
import json
import logging
import hashlib
from datetime import datetime, timedelta

logger = logging.getLogger("general_logger")

# Constants for session management
LICENSE_SESSION_KEY = 'validated_license'
LICENSE_EXPIRY_HOURS = 24


def get_license_hash(key):
    """Create a secure hash of the license key"""
    # Add a salt from settings for additional security
    salt = settings.SECRET_KEY[:16]
    return hashlib.sha256((key + salt).encode()).hexdigest()


def check_key(key):
    """Validate a license key against the Keygen API"""
    # Debug logging
    logger.info(f"Starting key validation with KEYGEN_ACCOUNT_ID: {settings.KEYGEN_ACCOUNT_ID}")
    logger.info(f"Key being validated: {key}")

    # Construct API endpoint
    api_endpoint = f"https://api.keygen.sh/v1/accounts/{settings.KEYGEN_ACCOUNT_ID}/licenses/actions/validate-key"
    logger.info(f"API endpoint: {api_endpoint}")

    # Prepare request data
    request_data = json.dumps({
        "meta": {
            "key": key
        }
    })
    logger.info(f"Request payload: {request_data}")

    # Make the API request
    try:
        response = requests.post(
            api_endpoint,
            headers={
                "Content-Type": "application/vnd.api+json",
                "Accept": "application/vnd.api+json"
            },
            data=request_data
        )

        # Log response details
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response content: {response.text[:200]}...")  # Log first 200 chars

        validation = response.json()
    except Exception as e:
        logger.error(f"Exception during API request: {str(e)}")
        return False

    if "errors" in validation:
        errs = validation["errors"]

        error_messages = '\n'.join(map(lambda e: "{} - {}".format(e["title"], e["detail"]).lower(), errs))
        logger.info(f"License validation failed: {error_messages}")
        return False

    valid = validation["meta"]["valid"]
    logger.info(f"License validation result: {valid}")

    return valid


def store_license_in_session(request, license_key):
    """Store the validated license key in the session"""
    # Check if sessions are available
    if hasattr(request, 'session'):
        # Create license hash for storage
        license_hash = get_license_hash(license_key)

        # Store in session with expiry information
        request.session[LICENSE_SESSION_KEY] = {
            'hash': license_hash,
            'expires': (datetime.now() + timedelta(hours=LICENSE_EXPIRY_HOURS)).isoformat()
        }
        # Ensure session doesn't expire with browser close
        request.session.set_expiry(LICENSE_EXPIRY_HOURS * 3600)  # in seconds
        logger.info("License stored in session")

        return True
    else:
        logger.warning("Session not available for license storage")
        return False


def is_license_valid(request):
    """Check if a valid license exists in the session"""
    # Try to get from session
    if hasattr(request, 'session') and LICENSE_SESSION_KEY in request.session:
        license_data = request.session[LICENSE_SESSION_KEY]

        # Check if license has expired
        try:
            expiry = datetime.fromisoformat(license_data['expires'])
            if datetime.now() < expiry:
                logger.info("Valid license found in session")
                return True
            else:
                logger.info("License in session has expired")
                # Clean up expired session data
                del request.session[LICENSE_SESSION_KEY]
        except (ValueError, KeyError) as e:
            logger.error(f"Error parsing license data from session: {str(e)}")
            # Session data is malformed, remove it
            del request.session[LICENSE_SESSION_KEY]

    logger.info("No valid license found in session")
    return False


def clear_license(request):
    """Clear license data from session"""
    # Clear from session
    if hasattr(request, 'session') and LICENSE_SESSION_KEY in request.session:
        del request.session[LICENSE_SESSION_KEY]

    logger.info("License data cleared")
    return