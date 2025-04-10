from django.shortcuts import render, HttpResponse, redirect
from django.views.generic import TemplateView
from django.conf import settings
from .utils import check_key, is_license_valid, store_license_in_session, clear_license

import base64
import boto3
import os
import logging
import requests
import io
import traceback

logger = logging.getLogger("general_logger")

S3_EXTENSIONS = (".aif", ".mp3", ".flac", ".wav")


def deserialize_zip_file(path, base64_encoded_content):
    try:
        downloads_dir = os.path.join(settings.MEDIA_ROOT, "downloads")
        os.makedirs(downloads_dir, exist_ok=True)

        zip_file_path = os.path.join(downloads_dir, path)
        with open(zip_file_path, 'wb') as f:
            f.write(base64.b64decode(base64_encoded_content))
        logger.info(f"Deserialized zip to {zip_file_path}")
        return True
    except Exception as e:
        logger.error(f"Deserialization failed: {e}")
        logger.error(traceback.format_exc())
        return False


class SettingsPage(TemplateView):
    def get(self, request):
        return render(request, 'setting.html')


class HomePage(TemplateView):
    def get(self, request):
        context = {'upload_section': True} if is_license_valid(request) else {'keygen_section': True}
        return render(request, 'home.html', context=context)


class ValidateKeygen(TemplateView):
    def post(self, request):
        try:
            logger.info("==== ValidateKeygen POST triggered ====")
            logger.info("Raw POST data: %s", request.POST)

            key = request.POST.get('keygen_license', '').strip()
            if not key:
                logger.warning("Empty license key submitted")
                return render(request, 'partials/file_upload_split.html', {
                    'keygen_section': True,
                    'error_message': 'License key cannot be empty!'
                })

            logger.info(f"Validating key: {key}")
            if check_key(key):
                try:
                    store_license_in_session(request, key)
                except Exception as e:
                    logger.error("Session store failed: %s", str(e))
                    return HttpResponse("Key valid but session storage failed", status=500)

                try:
                    return render(request, 'partials/file_upload_split.html', {'upload_section': True})
                except Exception as render_err:
                    logger.error("Render error: %s", str(render_err))
                    logger.error(traceback.format_exc())
                    return HttpResponse(f"<pre>Template render error:\n{traceback.format_exc()}</pre>", status=500)

            else:
                logger.warning("Invalid license key")
                return render(request, 'partials/file_upload_split.html', {
                    'keygen_section': True,
                    'error_message': 'License key is invalid. Please try again.'
                })

        except Exception as e:
            logger.error("Exception in ValidateKeygen: %s", str(e))
            logger.error(traceback.format_exc())
            return render(request, 'partials/file_upload_split.html', {
                'keygen_section': True,
                'error_message': f"Unexpected error:<br><pre>{traceback.format_exc()}</pre>"
            })


class UploadFile(TemplateView):
    def post(self, request):
        try:
            if settings.S3 is None:
                logger.error("S3 client not initialized")
                return render(request, 'partials/file_upload_split.html', {
                    'error_message': 'AWS S3 connection error',
                    'upload_section': True
                })

            if 'file' not in request.FILES:
                return render(request, 'partials/file_upload_split.html', {
                    'error_message': 'No file uploaded',
                    'upload_section': True
                })

            uploaded_file = request.FILES['file']
            logger.info(f"Received file: {uploaded_file.name}")

            if not uploaded_file.name.endswith(S3_EXTENSIONS):
                return render(request, 'partials/file_upload_split.html', {
                    'error_message': 'Unsupported file type. Must be .aif, .mp3, .flac, or .wav',
                    'upload_section': True
                })

            buffer = io.BytesIO()
            for chunk in uploaded_file.chunks():
                buffer.write(chunk)
            buffer.seek(0)

            settings.S3.put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=uploaded_file.name,
                Body=buffer.getvalue()
            )
            logger.info(f"Uploaded {uploaded_file.name} to S3")

            return render(request, 'partials/file_upload_split.html', {
                'file_name': uploaded_file.name,
                'split_section': True
            })

        except Exception as e:
            logger.error("Upload error: %s", str(e))
            logger.error(traceback.format_exc())
            return render(request, 'partials/file_upload_split.html', {
                'error_message': f"Upload failed: {str(e)}",
                'upload_section': True
            })


class SplitFile(TemplateView):
    def post(self, request):
        logger.info("=== SplitFile.post started ===")
        try:
            # Extract and validate file name
            file_name = request.POST.get('file_name', '')
            if not file_name:
                logger.error("No file_name provided in request")
                return render(request, 'partials/file_upload_split.html', {
                    'error_message': "Missing file name",
                    'upload_section': True
                })

            logger.info(f"Processing split request for file: {file_name}")

            # Validate Beam API configuration
            if not settings.BEAM_API_URL:
                logger.error("BEAM_API_URL not configured")
                return render(request, 'partials/file_upload_split.html', {
                    'error_message': "Split service not properly configured",
                    'upload_section': True
                })

            if not settings.BEAM_API_TOKEN:
                logger.error("BEAM_API_TOKEN not configured")
                return render(request, 'partials/file_upload_split.html', {
                    'error_message': "Split service authentication not configured",
                    'upload_section': True
                })

            # Prepare request to Beam API
            headers = {
                'Authorization': f"Bearer {settings.BEAM_API_TOKEN}",
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }

            payload = {'file_name': file_name}
            logger.info(f"Sending request to Beam API at {settings.BEAM_API_URL}")
            logger.info(f"Request payload: {payload}")

            # Make the API request with timeout
            try:
                response = requests.post(
                    settings.BEAM_API_URL,
                    headers=headers,
                    json=payload,
                    timeout=120  # 2 minute timeout
                )
            except requests.exceptions.Timeout:
                logger.error("Beam API request timed out after 120 seconds")
                return render(request, 'partials/file_upload_split.html', {
                    'error_message': "Processing timed out. Please try again or use a smaller file.",
                    'upload_section': True
                })
            except requests.exceptions.ConnectionError:
                logger.error(f"Connection error to Beam API at {settings.BEAM_API_URL}")
                return render(request, 'partials/file_upload_split.html', {
                    'error_message': "Could not connect to processing service. Please try again later.",
                    'upload_section': True
                })
            except requests.exceptions.RequestException as e:
                logger.error(f"Request to Beam API failed: {str(e)}")
                return render(request, 'partials/file_upload_split.html', {
                    'error_message': "Error communicating with processing service.",
                    'upload_section': True
                })

            # Process the API response
            logger.info(f"Beam API response status code: {response.status_code}")

            # For non-200 responses, try to extract meaningful error information
            if response.status_code != 200:
                try:
                    error_content = response.json()
                    logger.error(f"Beam API error response: {error_content}")
                    error_message = f"Processing service error: {error_content.get('error', 'Unknown error')}"
                except ValueError:
                    # Not JSON or other parsing error
                    logger.error(f"Beam API non-JSON error response: {response.text[:1000]}")
                    error_message = f"Processing service error (Status: {response.status_code})"

                return render(request, 'partials/file_upload_split.html', {
                    'error_message': error_message,
                    'upload_section': True
                })

            # Handle successful response
            try:
                result = response.json()
                logger.info(f"Successfully processed file. Result: {result}")

                if 'file_name' not in result:
                    logger.error(f"Missing file_name in Beam API response: {result}")
                    return render(request, 'partials/file_upload_split.html', {
                        'error_message': "Invalid response from processing service",
                        'upload_section': True
                    })

                # Success case - render download section
                return render(request, 'partials/file_upload_split.html', {
                    'zip_file_name': result['file_name'],
                    'download_section': True
                })

            except ValueError:
                logger.error(f"Could not parse Beam API JSON response: {response.text[:1000]}")
                return render(request, 'partials/file_upload_split.html', {
                    'error_message': "Invalid response from processing service",
                    'upload_section': True
                })

        except Exception as e:
            # Catch-all for any unexpected errors
            logger.error(f"Unexpected error in SplitFile view: {str(e)}")
            logger.error(traceback.format_exc())
            return render(request, 'partials/file_upload_split.html', {
                'error_message': "An unexpected error occurred. Please try again.",
                'upload_section': True
            })
        finally:
            logger.info("=== SplitFile.post completed ===")


class DownloadFile(TemplateView):
    def post(self, request):
        try:
            file_name = request.POST.get('zip_file_name')
            logger.info(f"Downloading file: {file_name}")

            buffer = io.BytesIO()
            s3_client = settings.S3

            s3_client.download_fileobj(settings.S3_BUCKET_NAME, file_name, buffer)
            logger.info(f"Downloaded {file_name}")

            try:
                s3_client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=file_name)
                logger.info(f"Deleted {file_name} from S3")
            except Exception as e:
                logger.warning(f"Failed to delete file: {e}")

            buffer.seek(0)
            response = HttpResponse(buffer.getvalue(), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{file_name}"'
            return response

        except Exception as e:
            logger.error("Download error: %s", str(e))
            logger.error(traceback.format_exc())
            return render(request, 'partials/file_upload_split.html', {
                'error_message': 'Download failed',
                'upload_section': True
            })


class LogoutView(TemplateView):
    def get(self, request):
        clear_license(request)
        return redirect('home')
