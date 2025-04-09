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


def deserialize_zip_file(path, base64_encoded_content):
    try:
        # Extract filename and base64 encoded content from JSON data
        downloads_dir = os.path.join(settings.MEDIA_ROOT, "downloads")
        if not os.path.exists(downloads_dir):
            os.makedirs(downloads_dir)
        zip_file_path = os.path.join(downloads_dir, f"{path}")

        # Decode the base64 encoded content
        decoded_content = base64.b64decode(base64_encoded_content)

        # Write the decoded content to a new file
        with open(zip_file_path, 'wb') as f:
            f.write(decoded_content)
        logger.info(f"Successfully deserialized zip file to {zip_file_path}")
        return True
    except Exception as e:
        logger.error(f"Error deserializing zip file: {str(e)}")
        logger.error(traceback.format_exc())
        return False


class SettingsPage(TemplateView):
    def get(self, request):
        return render(request, 'setting.html')


class HomePage(TemplateView):
    def get(self, request):
        # Check for a valid license in the session
        if is_license_valid(request):
            # User has a valid license, show the upload section directly
            context = {
                'upload_section': True
            }
        else:
            # No valid license, show the license entry form
            context = {
                'keygen_section': True
            }

        return render(request, 'home.html', context=context)


class ValidateKeygen(TemplateView):
    def post(self, request):
        try:
            logger.info(request.POST)
            key = request.POST.get('keygen_license')
            logger.info(key)

            validation = check_key(key=key)
            logger.info(validation)

            if validation:
                # Store the validated license in session
                store_license_in_session(request, key)

                context = {
                    'upload_section': True
                }
            else:
                context = {
                    'keygen_section': True,
                    'error_message': 'Key not valid!',
                }
            return render(request, 'partials/file_upload_split.html', context=context)
        except Exception as e:
            logger.error(f"Error validating keygen: {str(e)}")
            logger.error(traceback.format_exc())
            context = {
                'keygen_section': True,
                'error_message': f'Error validating key: {str(e)}',
            }
            return render(request, 'partials/file_upload_split.html', context=context)


class DownloadFile(TemplateView):
    def post(self, request):
        try:
            file_name = request.POST.get('zip_file_name')
            logger.info(f"Starting download of file: {file_name}")

            buffer = io.BytesIO()

            # Create a fresh S3 client for this request
            s3_client = boto3.client(
                's3',
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                region_name="us-west-2"
            )

            logger.info(f"Getting file from S3 bucket: {settings.S3_BUCKET_NAME}")

            try:
                s3_client.download_fileobj(settings.S3_BUCKET_NAME, file_name, buffer)
                logger.info(f"Successfully downloaded {file_name} from S3")

                try:
                    s3_client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=file_name)
                    logger.info(f"Successfully deleted {file_name} from S3")
                except Exception as e:
                    logger.error(f"Error deleting file from S3: {str(e)}")
                    # Continue even if delete fails

                buffer.seek(0)
                logger.info('Generating response')
                response = HttpResponse(buffer.getvalue(), content_type='application/octet-stream')
                response['Content-Disposition'] = f'attachment; filename="{file_name}"'
                return response

            except Exception as e:
                logger.error(f"S3 download error: {str(e)}")
                logger.error(traceback.format_exc())
                context = {
                    'error_message': f'Download failed: {str(e)}',
                    'upload_section': True
                }
                return render(request, 'partials/file_upload_split.html', context=context)

        except Exception as e:
            logger.error(f"General error in download: {str(e)}")
            logger.error(traceback.format_exc())
            context = {
                'error_message': 'Download processing error occurred',
                'upload_section': True
            }
            return render(request, 'partials/file_upload_split.html', context=context)


class SplitFile(TemplateView):
    def post(self, request):
        try:
            path = request.POST.get('file_name')
            logger.info(f"Starting split for file: {path}")

            json_data = {
                'file_name': path,
            }
            url = settings.BEAM_API_URL
            headers = {
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate',
                'Authorization': f'Bearer {settings.BEAM_API_TOKEN}',
                'Connection': 'keep-alive',
                'Content-Type': 'application/json'
            }
            logger.info('Pinging beam cloud API')
            try:
                response = requests.post(url, headers=headers, json=json_data)

                if response.status_code == 200:
                    logger.info('Got successful response from beam!')
                    json_response = response.json()
                    file_name = json_response['file_name']
                    logger.info(f"Beam returned file name: {file_name}")

                    context = {
                        'zip_file_name': file_name,
                        'download_section': True
                    }
                else:
                    logger.error(f'Beam failed with status code: {response.status_code}')
                    logger.error(f'Response content: {response.content}')
                    try:
                        error_details = response.json()
                        logger.error(f'Response JSON: {error_details}')
                    except:
                        logger.error('Could not parse JSON from error response')

                    context = {
                        'error_message': f"Analysis failed with status code: {response.status_code}",
                        'upload_section': True
                    }
            except Exception as e:
                logger.error(f"Error making request to beam: {str(e)}")
                logger.error(traceback.format_exc())
                context = {
                    'error_message': f"Error communicating with analysis service: {str(e)}",
                    'upload_section': True
                }

        except Exception as e:
            logger.error(f"General error in split: {str(e)}")
            logger.error(traceback.format_exc())
            context = {
                'error_message': 'Split processing error occurred',
                'upload_section': True
            }

        return render(request, 'partials/file_upload_split.html', context=context)


class UploadFile(TemplateView):
    def post(self, request):
        try:
            # Check if S3 client is properly initialized
            if settings.S3 is None:
                logger.error("S3 client is not initialized")
                context = {
                    'error_message': 'AWS S3 connection error',
                    'upload_section': True
                }
                return render(request, 'partials/file_upload_split.html', context=context)

            # Check if file was uploaded
            if 'file' not in request.FILES:
                logger.error("No file was uploaded")
                context = {
                    'error_message': 'No file was uploaded',
                    'upload_section': True
                }
                return render(request, 'partials/file_upload_split.html', context=context)

            uploaded_file = request.FILES['file']
            logger.info(f"Processing uploaded file: {uploaded_file.name}")

            # Check file extension
            file_extensions = (".aif", ".mp3", ".flac", ".wav")
            if uploaded_file.name.endswith(file_extensions):
                logger.info(f"File extension is valid: {uploaded_file.name}")

                # Create a BytesIO buffer
                buffer = io.BytesIO()

                # Write the chunks into the buffer
                for chunk in uploaded_file.chunks():
                    buffer.write(chunk)

                # Reset the buffer position to the beginning
                buffer.seek(0)

                # Get buffer size for logging
                buffer_size = len(buffer.getvalue())
                logger.info(f"File size in buffer: {buffer_size} bytes")

                try:
                    # Log bucket name for debugging
                    logger.info(f"Attempting to upload to bucket: {settings.S3_BUCKET_NAME}")

                    # Try the upload
                    settings.S3.put_object(
                        Bucket=settings.S3_BUCKET_NAME,
                        Key=uploaded_file.name,
                        Body=buffer.getvalue()
                    )
                    logger.info(f"Successfully uploaded {uploaded_file.name} to S3")

                    context = {
                        'file_name': uploaded_file.name,
                        'split_section': True
                    }
                except Exception as e:
                    logger.error(f"S3 upload error: {str(e)}")
                    logger.error(traceback.format_exc())
                    context = {
                        'error_message': f'Upload failed: {str(e)}',
                        'upload_section': True
                    }
            else:
                logger.warning(f"Invalid file extension: {uploaded_file.name}")
                context = {
                    'error_message': 'File type not supported! Please upload .aif, .mp3, .flac, or .wav files.',
                    'upload_section': True
                }

        except Exception as e:
            logger.error(f"General error in upload: {str(e)}")
            logger.error(traceback.format_exc())
            context = {
                'error_message': f'Upload processing error occurred: {str(e)}',
                'upload_section': True
            }

        return render(request, 'partials/file_upload_split.html', context=context)

class LogoutView(TemplateView):
    def get(self, request):
        # Clear license from session
        clear_license(request)
        return redirect('home')