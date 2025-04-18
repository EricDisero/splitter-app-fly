import os
import json
import uuid
import logging
import traceback
import shutil
from django.shortcuts import render, redirect
from django.views.generic import TemplateView, View
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
from .utils import check_key, is_license_valid, store_license_in_session, clear_license
from .mvsep_processor import MVSepProcessor

logger = logging.getLogger("general_logger")


# Import S3 client directly to avoid circular reference
def get_s3():
    """Get S3 client from settings.py function"""
    from splitter_django.settings import get_s3_client
    return get_s3_client()


class HomePage(TemplateView):
    def get(self, request):
        context = {'upload_section': True} if is_license_valid(request) else {'keygen_section': True}
        return render(request, 'home.html', context)


class ValidateKeygen(TemplateView):
    def post(self, request):
        logger.info("ValidateKeygen POST received")
        key = request.POST.get('keygen_license', '').strip()
        if not key:
            return render(request, 'partials/file_upload_split.html', {
                'keygen_section': True,
                'error_message': 'License key cannot be empty!'
            })

        logger.info(f"Validating license key (first 4 chars): {key[:4]}...")
        if check_key(key):
            logger.info("License key valid, storing in session")
            store_license_in_session(request, key)
            return render(request, 'partials/file_upload_split.html', {'upload_section': True})

        logger.warning("Invalid license key provided")
        return render(request, 'partials/file_upload_split.html', {
            'keygen_section': True,
            'error_message': 'License key is invalid. Please try again.'
        })


class UploadFile(TemplateView):
    def post(self, request):
        logger.info("UploadFile POST received")
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            logger.warning("No file uploaded")
            return render(request, 'partials/file_upload_split.html', {
                'upload_section': True,
                'error_message': 'No file uploaded.'
            })

        logger.info(f"File uploaded: {uploaded_file.name} ({uploaded_file.size} bytes)")

        # Validate file extension
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in [".wav", ".mp3", ".flac", ".aif"]:
            logger.warning(f"Unsupported file type: {ext}")
            return render(request, 'partials/file_upload_split.html', {
                'upload_section': True,
                'error_message': f"Unsupported file type: {ext}. Must be .wav, .mp3, .flac, or .aif."
            })

        # Generate a unique ID for the file
        file_id = uuid.uuid4().hex
        s3_key = f"uploads/{file_id}{ext}"
        logger.info(f"Generated S3 key: {s3_key}")

        # Get S3 client
        s3_client = get_s3()
        if not s3_client:
            logger.error("S3 client not initialized")
            return render(request, 'partials/file_upload_split.html', {
                'upload_section': True,
                'error_message': 'Cloud storage not available. Please try again later.'
            })

        # Upload file to S3
        try:
            logger.info(f"Uploading to S3 bucket: {settings.S3_BUCKET_NAME}")
            s3_client.upload_fileobj(uploaded_file, settings.S3_BUCKET_NAME, s3_key)
            logger.info(f"Successfully uploaded to S3: {s3_key}")

            # Return template with file info for splitting
            return render(request, 'partials/file_upload_split.html', {
                'file_name': uploaded_file.name,
                's3_key': s3_key,
                'split_section': True
            })
        except Exception as e:
            logger.error(f"S3 upload error: {str(e)}")
            logger.error(traceback.format_exc())
            return render(request, 'partials/file_upload_split.html', {
                'upload_section': True,
                'error_message': f"Upload failed: {str(e)}"
            })


class SplitFile(TemplateView):
    def post(self, request):
        logger.info("=== SplitFile POST started ===")
        try:
            # Log request data for debugging
            logger.info(f"POST data keys: {list(request.POST.keys())}")

            # Get file information
            s3_key = request.POST.get('s3_key')
            file_name = request.POST.get('file_name')
            logger.info(f"File to process: {file_name} (S3 key: {s3_key})")

            # Validate input
            if not s3_key or not file_name:
                logger.error("Missing required parameters")
                return render(request, 'partials/file_upload_split.html', {
                    'upload_section': True,
                    'error_message': "Missing file information."
                })

            # Get S3 client
            s3_client = get_s3()
            if not s3_client:
                logger.error("Failed to initialize S3 client")
                return render(request, 'partials/file_upload_split.html', {
                    'upload_section': True,
                    'error_message': 'Cloud storage not available. Please try again later.'
                })

            # Download file from S3
            local_path = f"/tmp/{uuid.uuid4().hex}_{os.path.basename(s3_key)}"
            logger.info(f"Downloading from S3 to: {local_path}")
            s3_client.download_file(settings.S3_BUCKET_NAME, s3_key, local_path)
            logger.info(f"Download successful")

            # Check if file exists and has content
            if not os.path.exists(local_path) or os.path.getsize(local_path) == 0:
                raise Exception(f"Downloaded file is missing or empty: {local_path}")

            # Create output directory
            local_output_dir = f"/tmp/{uuid.uuid4().hex}"
            os.makedirs(local_output_dir, exist_ok=True)
            logger.info(f"Created output directory: {local_output_dir}")

            # Initialize MVSEP processor
            api_token = settings.MVSEP_API_TOKEN
            if not api_token:
                raise Exception("MVSEP API token not configured")

            # Process with first/last 4 chars of token for logging security
            logger.info(
                f"Starting MVSep processing with API token: {api_token[:4]}...{api_token[-4:] if len(api_token) > 8 else ''}")
            processor = MVSepProcessor(api_token=api_token, temp_dir=settings.MVSEP_TEMP_DIR)

            try:
                # Process the file through the cascaded splitting pipeline
                logger.info(f"Processing file: {local_path}")
                stem_paths = processor.process_file(local_path, local_output_dir)
                logger.info(f"Processing complete: {len(stem_paths)} stems generated")

                # Upload stems to S3
                stem_files = []
                base_name = os.path.splitext(file_name)[0]

                for stem_type, path in stem_paths.items():
                    # Generate a nice filename for the S3 object
                    s3_stem_key = f"downloads/{uuid.uuid4().hex}_{os.path.basename(path)}"
                    logger.info(f"Uploading stem '{stem_type}' to S3: {s3_stem_key}")

                    # Upload to S3
                    s3_client.upload_file(path, settings.S3_BUCKET_NAME, s3_stem_key)

                    # Add to our list with proper metadata
                    stem_files.append({
                        "file_name": f"{base_name} {stem_type.capitalize()}.wav",
                        "s3_key": s3_stem_key,
                        "stem_type": stem_type
                    })
            finally:
                # Clean up processor resources
                processor.cleanup()

            # Cleanup temporary files
            try:
                os.remove(local_path)
                shutil.rmtree(local_output_dir, ignore_errors=True)
                logger.info("Cleaned up temporary files")
            except Exception as e:
                logger.warning(f"Cleanup error (non-critical): {str(e)}")

            # Delete original uploaded file from S3
            try:
                logger.info(f"Deleting original uploaded file from S3: {s3_key}")
                s3_client.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
            except Exception as e:
                logger.warning(f"Failed to delete uploaded file {s3_key}: {str(e)}")

            # Return download page
            logger.info(f"Rendering download page with {len(stem_files)} stems")
            return render(request, 'partials/file_upload_split.html', {
                'zip_file_name': os.path.splitext(file_name)[0],
                'stem_files_json': json.dumps(stem_files),
                'download_section': True
            })

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Processing error: {error_msg}")
            logger.error(traceback.format_exc())
            return render(request, 'partials/file_upload_split.html', {
                'upload_section': True,
                'error_message': f"Processing error: {error_msg}"
            })
        finally:
            logger.info("=== SplitFile POST completed ===")


class DownloadFile(View):
    def post(self, request):
        logger.info("DownloadFile POST received")
        try:
            # Get parameters
            base_name = request.POST.get('base_name')
            stem_files_json = request.POST.get('stem_files')

            if not base_name or not stem_files_json:
                logger.error("Missing parameters for download")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Missing required parameters'
                }, status=400)

            # Parse stems JSON
            try:
                stem_files = json.loads(stem_files_json)
                logger.info(f"Processing {len(stem_files)} stems for download")
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON: {str(e)}")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid stem files data'
                }, status=400)

            # Get S3 client
            s3_client = get_s3()
            if not s3_client:
                logger.error("S3 client not available for generating download URLs")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Storage service unavailable'
                }, status=500)

            # Generate presigned URLs
            download_urls = []
            for stem in stem_files:
                s3_key = stem.get('s3_key')
                file_name = stem.get('file_name')
                stem_type = stem.get('stem_type', 'unknown')

                if not s3_key or not file_name:
                    logger.warning(f"Skipping invalid stem entry: {stem}")
                    continue

                try:
                    logger.info(f"Generating presigned URL for {stem_type}: {s3_key}")
                    url = s3_client.generate_presigned_url(
                        ClientMethod='get_object',
                        Params={
                            'Bucket': settings.S3_BUCKET_NAME,
                            'Key': s3_key,
                            'ResponseContentDisposition': f'attachment; filename="{file_name}"'
                        },
                        ExpiresIn=21600  # 6 hours
                    )
                    download_urls.append({
                        "url": url,
                        "filename": file_name,
                        "stem_type": stem_type
                    })
                except Exception as e:
                    logger.error(f"Error generating URL for {s3_key}: {str(e)}")
                    download_urls.append({
                        "url": None,
                        "filename": file_name,
                        "stem_type": stem_type,
                        "error": str(e)
                    })

            # Schedule quick delayed cleanup in the background (1 minute)
            self._schedule_delayed_cleanup(stem_files_json)

            # Return download URLs
            logger.info(f"Returning {len(download_urls)} download URLs")
            return JsonResponse({
                'status': 'success',
                'base_name': base_name,
                'download_urls': download_urls
            })

        except Exception as e:
            logger.error(f"Download preparation error: {str(e)}")
            logger.error(traceback.format_exc())
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    def _schedule_delayed_cleanup(self, stem_files_json):
        """Schedule a background task to clean up files after a short delay"""
        import threading
        import time

        def delayed_cleanup():
            # Wait for 70 seconds to ensure downloads have had time to start
            time.sleep(70)  # 70 seconds

            try:
                logger.info("Starting quick delayed cleanup of S3 files (1-minute delay)")
                stem_files = json.loads(stem_files_json)

                # Get S3 client
                s3_client = get_s3()
                if not s3_client:
                    logger.error("S3 client not available for cleanup")
                    return

                # Delete files from S3
                deleted = []
                failed = []

                for item in stem_files:
                    # Handle both dictionary and string formats
                    if isinstance(item, dict):
                        s3_key = item.get('s3_key')
                    elif isinstance(item, str):
                        s3_key = item
                    else:
                        logger.warning(f"Skipping invalid item type: {type(item)}")
                        continue

                    if not s3_key:
                        continue

                    try:
                        logger.info(f"Deleting from S3: {s3_key}")
                        s3_client.delete_object(
                            Bucket=settings.S3_BUCKET_NAME,
                            Key=s3_key
                        )
                        deleted.append(s3_key)
                    except Exception as e:
                        logger.error(f"Failed to delete {s3_key}: {str(e)}")
                        failed.append({'key': s3_key, 'error': str(e)})

                logger.info(f"Quick cleanup complete. Deleted: {len(deleted)}, Failed: {len(failed)}")

            except Exception as e:
                logger.error(f"Error in delayed cleanup: {str(e)}")
                logger.error(traceback.format_exc())

        # Start the cleanup task in a background thread
        cleanup_thread = threading.Thread(target=delayed_cleanup)
        cleanup_thread.daemon = True  # Allow the app to exit even if thread is running
        cleanup_thread.start()
        logger.info("Scheduled quick 70 second delayed cleanup task")


@method_decorator(csrf_exempt, name='dispatch')
class CleanupS3View(View):
    def post(self, request):
        logger.info("CleanupS3View POST received")
        try:
            # Parse request body
            try:
                body = json.loads(request.body or '{}')
                stem_files_json = body.get('stem_files', '[]')

                # Handle string or direct JSON
                if isinstance(stem_files_json, str):
                    stem_files = json.loads(stem_files_json)
                else:
                    stem_files = stem_files_json

                logger.info(f"Cleaning up {len(stem_files)} files from S3")
            except json.JSONDecodeError as e:
                logger.error(f"JSON parsing error: {str(e)}")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Invalid JSON data'
                }, status=400)

            # Get S3 client
            s3_client = get_s3()
            if not s3_client:
                logger.error("S3 client not available for cleanup")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Storage service unavailable'
                }, status=500)

            # Delete files from S3
            deleted = []
            failed = []
            for item in stem_files:
                # Handle both dictionary and string formats
                if isinstance(item, dict):
                    s3_key = item.get('s3_key')
                elif isinstance(item, str):
                    s3_key = item
                else:
                    logger.warning(f"Skipping invalid item type: {type(item)}")
                    continue

                if not s3_key:
                    continue

                try:
                    logger.info(f"Deleting from S3: {s3_key}")
                    s3_client.delete_object(
                        Bucket=settings.S3_BUCKET_NAME,
                        Key=s3_key
                    )
                    deleted.append(s3_key)
                except Exception as e:
                    logger.error(f"Failed to delete {s3_key}: {str(e)}")
                    failed.append({'key': s3_key, 'error': str(e)})

            # Return results
            return JsonResponse({
                'status': 'success',
                'deleted_count': len(deleted),
                'failed_count': len(failed),
                'deleted_files': deleted,
                'failed_files': failed
            })

        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")
            logger.error(traceback.format_exc())
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)


class LogoutView(TemplateView):
    def get(self, request):
        logger.info("Logout requested")
        clear_license(request)
        return redirect('home')