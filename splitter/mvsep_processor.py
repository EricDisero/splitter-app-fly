"""
MVSep Processing Service - Handles the cascade of audio processing steps using the MVSep API.
This service coordinates the multi-step process for extracting vocal, drums, bass, and individual drum stems.
"""

import os
import time
import logging
import requests
import json
from typing import Dict, List, Optional, Tuple, Any
import soundfile as sf
import numpy as np
import tempfile
from pathlib import Path
import scipy.signal
import shutil

logger = logging.getLogger("general_logger")

class MVSepProcessor:
    MVSEP_API_CREATE_URL = "https://mvsep.com/api/separation/create"
    MVSEP_API_GET_URL = "https://mvsep.com/api/separation/get"

    # MVSep separation type IDs
    SEP_BS_ROFORMER = 40  # Vocals/Instrumental
    SEP_DRUMS = 44        # Drums/Other
    SEP_BASS = 41         # Bass/Other
    SEP_DRUMSEP = 37      # Drum components

    # Output format
    OUTPUT_WAV = 1

    def __init__(self, api_token: str, temp_dir: Optional[str] = None):
        self.api_token = api_token
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.mkdtemp())
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized MVSepProcessor with temp dir: {self.temp_dir}")

    def process_file(self, file_path: str, output_dir: str) -> Dict[str, str]:
        """
        Process an audio file through the cascaded stem extraction pipeline.

        Args:
            file_path: Path to the input audio file
            output_dir: Directory to store output stems

        Returns:
            Dictionary mapping stem types to their file paths
        """
        try:
            # Create output directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)

            # Get base name for output files (original filename without extension)
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            logger.info(f"Processing file: {file_path} (base name: {base_name})")

            # Step 1: Preprocess the input file
            preprocessed_path = self._preprocess_input(file_path)

            # Step 2: Extract vocals with BS Roformer
            logger.info("Step 1: Extracting vocals with BS Roformer")
            vocal_path, instrumental_path = self._extract_vocals(preprocessed_path)

            # Step 3: Extract drums from instrumental
            logger.info("Step 2: Extracting drums from instrumental")
            drums_path, no_drums_path = self._extract_drums(instrumental_path)

            # Step 4: Extract bass from no_drums
            logger.info("Step 3: Extracting bass from no_drums")
            bass_path, no_bass_path = self._extract_bass(no_drums_path)

            # Step 5: Extract individual drum components
            logger.info("Step 4: Extracting individual drum components")
            drum_stems = self._extract_drum_components(drums_path)

            # Step 6: Generate hats through phase cancellation
            logger.info("Step 5: Generating hats through phase cancellation")
            hats_path = self._generate_hats(drums_path, drum_stems)

            # Step 7: Generate EE (everything else) through phase cancellation
            logger.info("Step 6: Generating EE through phase cancellation")
            ee_path = self._generate_ee(preprocessed_path, vocal_path, drums_path, bass_path)

            # Step 8: Prepare final output files with proper naming
            logger.info("Step 7: Preparing final output files")
            return self._prepare_final_output(
                base_name, output_dir, vocal_path, drums_path, bass_path,
                drum_stems, hats_path, ee_path
            )

        except Exception as e:
            logger.error(f"Error generating EE: {str(e)}")
            raise

    def _prepare_final_output(
            self,
            base_name: str,
            output_dir: str,
            vocal_path: str,
            drums_path: str,
            bass_path: str,
            drum_stems: Dict[str, str],
            hats_path: str,
            ee_path: str
    ) -> Dict[str, str]:
        """
        Prepare the final output files with proper naming.

        We only want 7 final stems:
        - vocals
        - kick
        - snare
        - toms
        - hats
        - bass
        - ee (everything else/instruments)

        Args:
            base_name: Base name for the files
            output_dir: Directory to store the output files
            vocal_path: Path to the vocals file
            drums_path: Path to the drums file (not used in final output)
            bass_path: Path to the bass file
            drum_stems: Dictionary with paths to individual drum component files
            hats_path: Path to the hats file
            ee_path: Path to the EE file

        Returns:
            Dictionary mapping stem type to final file path
        """
        logger.info(f"Preparing final output files with base name: {base_name}")
        output_files = {}
        output_dir = Path(output_dir)

        # Define output file paths with proper naming
        stem_files = {
            'vocals': f"{base_name} Vocals.wav",
            'kick': f"{base_name} Kick.wav",
            'snare': f"{base_name} Snare.wav",
            'toms': f"{base_name} Toms.wav",
            'hats': f"{base_name} Hats.wav",
            'bass': f"{base_name} Bass.wav",
            'ee': f"{base_name} EE.wav"
        }

        # Copy files to output directory with proper naming
        try:
            # Vocal stem
            shutil.copy(vocal_path, output_dir / stem_files['vocals'])
            output_files['vocals'] = str(output_dir / stem_files['vocals'])

            # Bass stem
            shutil.copy(bass_path, output_dir / stem_files['bass'])
            output_files['bass'] = str(output_dir / stem_files['bass'])

            # Drum component stems
            shutil.copy(drum_stems['kick'], output_dir / stem_files['kick'])
            output_files['kick'] = str(output_dir / stem_files['kick'])

            shutil.copy(drum_stems['snare'], output_dir / stem_files['snare'])
            output_files['snare'] = str(output_dir / stem_files['snare'])

            shutil.copy(drum_stems['toms'], output_dir / stem_files['toms'])
            output_files['toms'] = str(output_dir / stem_files['toms'])

            # Generated stems
            shutil.copy(hats_path, output_dir / stem_files['hats'])
            output_files['hats'] = str(output_dir / stem_files['hats'])

            shutil.copy(ee_path, output_dir / stem_files['ee'])
            output_files['ee'] = str(output_dir / stem_files['ee'])

            logger.info(f"Created {len(output_files)} output files in {output_dir}")
            return output_files

        except Exception as e:
            logger.error(f"Error preparing final output: {str(e)}")
            raise

    def _start_separation_job(
            self,
            file_path: str,
            sep_type: int,
            add_opt1: Optional[str] = None,
            add_opt2: Optional[str] = None,
            add_opt3: Optional[str] = None
    ) -> str:
        """
        Start a separation job on MVSep API.

        Args:
            file_path: Path to the audio file
            sep_type: Separation type ID
            add_opt1: Optional parameter 1
            add_opt2: Optional parameter 2
            add_opt3: Optional parameter 3

        Returns:
            Separation hash for tracking the job
        """
        logger.info(f"Starting separation job for {file_path} with type {sep_type}")

        # Use exact parameters from original implementation for default case
        if sep_type == 26:  # vocals + instrumental - our default case
            form_data = {
                'api_token': self.api_token,
                'sep_type': '26',  # vocals + instrumental
                'add_opt1': '0',   # standard output
                'add_opt2': '6',   # best quality model
                'output_format': '1',  # wav
                'is_demo': '0'     # <- THIS is the fix
            }
        else:
            # For other sep_types, build parameters dynamically
            form_data = {
                'api_token': self.api_token,
                'sep_type': str(sep_type),
                'output_format': str(self.OUTPUT_WAV),
                'is_demo': '0'  # Important to avoid sharing user files
            }

            # Add optional parameters if provided
            if add_opt1 is not None:
                form_data['add_opt1'] = add_opt1
            if add_opt2 is not None:
                form_data['add_opt2'] = add_opt2
            if add_opt3 is not None:
                form_data['add_opt3'] = add_opt3

        # Prepare the file to upload
        files = {
            'audiofile': (os.path.basename(file_path), open(file_path, 'rb'))
        }

        try:
            logger.info(f"📤 Uploading to MVSEP: {file_path}")
            logger.info(f"📦 Payload: sep_type={form_data['sep_type']} " +
                       f"add_opt1={form_data.get('add_opt1', 'None')} " +
                       f"add_opt2={form_data.get('add_opt2', 'None')} " +
                       f"format={form_data['output_format']}")

            response = requests.post(
                self.MVSEP_API_CREATE_URL,
                data=form_data,
                files=files
            )

            # Check response
            logger.info(f"📬 MVSEP response: {response.status_code} — {response.text[:200]}...")

            if response.status_code != 200:
                logger.error(f"🔥 MVSEP API ERROR: {response.status_code} — {response.text}")
                raise Exception(f"MVSep API error: {response.status_code}")

            response_data = response.json()

            if not response_data.get('success'):
                error_message = response_data.get('data', {}).get('message', 'Unknown error')
                logger.error(f"❌ Job creation failed: {error_message}")
                raise Exception(f"MVSep job creation failed: {error_message}")

            separation_hash = response_data.get('data', {}).get('hash')

            if not separation_hash:
                raise Exception("No separation hash returned from MVSep API")

            logger.info(f"✅ Job created successfully. Hash: {separation_hash}")
            return separation_hash

        except Exception as e:
            logger.error(f"Error starting separation job: {str(e)}")
            raise
        finally:
            # Close the file
            files['audiofile'][1].close()

    def _wait_for_completion(self, separation_hash: str, max_attempts: int = 120, delay: int = 5) -> Dict[str, Any]:
        """
        Poll the MVSep API until the job is complete.

        Args:
            separation_hash: The hash of the separation job
            max_attempts: Maximum number of polling attempts
            delay: Delay between polling attempts (seconds)

        Returns:
            Result data from the completed job
        """
        logger.info(f"Polling MVSEP for job {separation_hash}")
        attempts = 0

        while attempts < max_attempts:
            try:
                response = requests.get(
                    f"{self.MVSEP_API_GET_URL}?hash={separation_hash}"
                )

                if response.status_code != 200:
                    logger.error(f"MVSep API error: {response.status_code} - {response.text}")
                    raise Exception(f"MVSep API error: {response.status_code}")

                response_data = response.json()

                if not response_data.get('success'):
                    error_message = response_data.get('data', {}).get('message', 'Unknown error')
                    logger.error(f"MVSep job check failed: {error_message}")
                    raise Exception(f"MVSep job check failed: {error_message}")

                status = response_data.get('status')
                logger.info(f"Job status: {status}")

                if status == 'done':
                    return response_data.get('data', {})
                elif status == 'failed':
                    error_message = response_data.get('data', {}).get('message', 'Unknown error')
                    logger.error(f"MVSep job failed: {error_message}")
                    raise Exception(f"MVSep job failed: {error_message}")
                elif status in ['waiting', 'processing', 'distributing', 'merging']:
                    # Job is still in progress, wait and try again
                    time.sleep(delay)
                    attempts += 1
                else:
                    logger.error(f"Unknown job status: {status}")
                    raise Exception(f"Unknown job status: {status}")

            except Exception as e:
                if "MVSep" not in str(e):
                    logger.error(f"Error checking job status: {str(e)}")
                raise

        # If we get here, we've exceeded the maximum attempts
        raise Exception(f"Timed out waiting for job {separation_hash} to complete")

    def _download_file(self, url: str, save_path: str) -> str:
        """
        Download a file from the given URL and save it to the specified path.

        Args:
            url: URL to download from
            save_path: Path to save the file to

        Returns:
            Path to the downloaded file
        """
        logger.info(f"⬇️ Downloading from {url} → {save_path}")

        try:
            response = requests.get(url, stream=True)

            if response.status_code != 200:
                logger.error(f"Download error: {response.status_code} - {response.text}")
                raise Exception(f"Download error: {response.status_code}")

            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            logger.info(f"✅ Saved to {save_path}")
            return str(save_path)

        except Exception as e:
            logger.error(f"Error downloading file: {str(e)}")
            raise

    def cleanup(self):
        """
        Clean up temporary files.
        """
        try:
            logger.info(f"Cleaning up temporary directory: {self.temp_dir}")
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            logger.info("Cleanup complete")
        except Exception as e:
            logger.warning(f"Error during cleanup: {str(e)}")

            logger.error(f"Error cleaning temp dir {self.temp_dir}: {str(e)}")
            raise

    def _preprocess_input(self, file_path: str) -> str:
        """
        Preprocess input file to ensure compatibility:
        1. Convert non-WAV formats to WAV
        2. Ensure 44.1kHz sample rate
        3. NO gain adjustments - preserve original levels exactly

        Args:
            file_path: Path to the input audio file

        Returns:
            Path to the preprocessed audio file
        """
        logger.info(f"Preprocessing: {file_path}")
        try:
            # Get file extension
            file_ext = os.path.splitext(file_path)[1].lower()

            # Check if file is WAV
            is_wav = file_ext == '.wav'

            # For non-WAV files, we'll use a library that can handle different formats
            if not is_wav:
                logger.info(f"Converting {file_ext} to WAV format")
                # We can use soundfile with additional libraries like pydub if needed
                try:
                    # First attempt: Try with soundfile directly
                    data, sr = sf.read(file_path)
                    logger.info(f"Loaded {file_ext} file using soundfile")
                except Exception as sf_error:
                    logger.warning(f"Soundfile couldn't load {file_ext} file: {sf_error}")

                    # Second attempt: Try with pydub if available
                    try:
                        import pydub
                        from pydub import AudioSegment

                        # Load file with pydub
                        logger.info(f"Trying to load with pydub")
                        if file_ext == '.mp3':
                            audio = AudioSegment.from_mp3(file_path)
                        elif file_ext == '.flac':
                            audio = AudioSegment.from_file(file_path, format="flac")
                        elif file_ext == '.aif' or file_ext == '.aiff':
                            audio = AudioSegment.from_file(file_path, format="aiff")
                        else:
                            audio = AudioSegment.from_file(file_path)

                        logger.info(f"Successfully loaded audio with pydub")

                        # Export as temporary WAV for further processing
                        temp_wav = self.temp_dir / f"temp_converted{os.path.basename(file_path)}.wav"
                        audio.export(temp_wav, format="wav")

                        # Now load with soundfile
                        data, sr = sf.read(temp_wav)
                        logger.info(f"Converted to WAV using pydub")

                    except ImportError:
                        logger.error("Pydub not available for audio conversion")
                        raise Exception(f"Cannot process {file_ext} file - pydub library not available")
                    except Exception as pydub_error:
                        logger.error(f"Pydub conversion failed: {pydub_error}")
                        raise Exception(f"Failed to convert {file_ext} file to WAV: {pydub_error}")
            else:
                # For WAV files, load directly
                data, sr = sf.read(file_path)
                logger.info(f"Loaded WAV file: {sr}Hz")

            # Ensure we have a target sample rate of 44.1kHz
            target_sr = 44100

            # Resample if needed
            if sr != target_sr:
                logger.info(f"Resampling from {sr}Hz to {target_sr}Hz")
                if data.ndim == 1:  # Mono
                    data = scipy.signal.resample_poly(data, target_sr, sr)
                else:  # Stereo
                    data = scipy.signal.resample_poly(data, target_sr, sr, axis=0)
            else:
                logger.info("Sample rate already 44.1kHz")

            # NO gain adjustment - preserving original levels exactly

            # Save preprocessed file
            out_path = self.temp_dir / f"preprocessed_{Path(file_path).name}.wav"
            sf.write(out_path, data, target_sr, subtype='FLOAT')
            logger.info(f"Saved preprocessed file: {out_path}")

            return str(out_path)

        except Exception as e:
            logger.error(f"Error preprocessing file: {str(e)}")
            raise

    def _extract_vocals(self, file_path: str) -> Tuple[str, str]:
        """
        Extract vocals from the source file using BS Roformer.

        Args:
            file_path: Path to the audio file

        Returns:
            Tuple of (vocals_path, instrumental_path)
        """
        logger.info(f"Extracting vocals from: {file_path}")

        # Start the separation job
        separation_hash = self._start_separation_job(
            file_path,
            self.SEP_BS_ROFORMER,
            add_opt1="29"  # ver 2024.08 (SDR vocals: 11.31, SDR instrum: 17.62)
        )

        # Wait for job completion
        result_data = self._wait_for_completion(separation_hash)

        # Download the separated files
        files_info = result_data.get('files', [])

        # Log all files found in the response
        logger.info(f"API returned {len(files_info)} files")
        for i, file_info in enumerate(files_info):
            filename = file_info.get('filename', '')
            url = file_info.get('url', '')
            logger.info(f"File {i+1}: filename='{filename}', url={url[:50] if url else 'None'}...")
            # Log additional file data that might help identify the files
            if 'type' in file_info:
                logger.info(f"File {i+1} type: {file_info['type']}")

        # If we have exactly 2 files in a vocals/instrumental separation, and no filenames,
        # we can assume the first file is vocals and the second is instrumental
        if len(files_info) == 2 and all(not file_info.get('filename') for file_info in files_info):
            logger.info("Using positional assumption: first file is vocals, second is instrumental")

            # Try to get URLs
            if files_info[0].get('url') and files_info[1].get('url'):
                vocal_path = self._download_file(files_info[0]['url'], self.temp_dir / 'vocals.wav')
                instrumental_path = self._download_file(files_info[1]['url'], self.temp_dir / 'instrumental.wav')

                # Log successful download
                if vocal_path and instrumental_path:
                    logger.info("Successfully downloaded vocals and instrumental using positional assumption")
                    return vocal_path, instrumental_path

        # If positional assumption failed or wasn't applicable, try pattern matching
        vocal_path = None
        instrumental_path = None

        # Check each file for identifying information
        for file_info in files_info:
            url = file_info.get('url')
            if not url:
                continue

            # Check filename first
            filename = file_info.get('filename', '').lower()
            file_type = file_info.get('type', '').lower()

            # Extract name from URL if filename is empty
            if not filename and url:
                # Try to extract filename from URL
                url_parts = url.split('/')
                if url_parts:
                    filename = url_parts[-1].lower()

            # Try to identify file type from filename or other properties
            is_vocal = False
            is_instrumental = False

            # Check file_type if available
            if file_type:
                is_vocal = 'vocal' in file_type or 'voc' in file_type
                is_instrumental = 'instrum' in file_type or 'accomp' in file_type or 'other' in file_type

            # Check filename patterns
            if not (is_vocal or is_instrumental) and filename:
                is_vocal = 'vocal' in filename or 'voc' in filename or '_voc_' in filename
                is_instrumental = ('instrum' in filename or 'accomp' in filename or
                                'other' in filename or '_other' in filename)

            # Use URL as fallback
            if not (is_vocal or is_instrumental) and url:
                is_vocal = 'vocal' in url or 'voc' in url or '_voc_' in url
                is_instrumental = ('instrum' in url or 'accomp' in url or
                                'other' in url or '_other' in url)

            # Download the identified files
            if is_vocal and not vocal_path:
                vocal_path = self._download_file(url, self.temp_dir / 'vocals.wav')
                logger.info(f"Found vocals file: url={url[:50]}...")

            elif is_instrumental and not instrumental_path:
                instrumental_path = self._download_file(url, self.temp_dir / 'instrumental.wav')
                logger.info(f"Found instrumental file: url={url[:50]}...")

        # If we couldn't find the expected files, log detailed info and raise exception
        if not vocal_path or not instrumental_path:
            missing = []
            if not vocal_path:
                missing.append("vocals")
            if not instrumental_path:
                missing.append("instrumental")

            # Log more details
            logger.error(f"Missing output files: {', '.join(missing)}")
            file_details = []
            for f in files_info:
                details = {}
                for key in ['url', 'filename', 'type']:
                    if key in f:
                        details[key] = f[key]
                file_details.append(details)
            logger.error(f"Available files: {file_details}")

            raise Exception(f"Failed to extract vocals: output files not found ({', '.join(missing)} missing)")

        return vocal_path, instrumental_path

    def _extract_drums(self, instrumental_path: str) -> Tuple[str, str]:
        """
        Extract drums from the instrumental file.

        Args:
            instrumental_path: Path to the instrumental audio file

        Returns:
            Tuple of (drums_path, no_drums_path)
        """
        logger.info(f"Extracting drums from: {instrumental_path}")

        # Start the separation job
        separation_hash = self._start_separation_job(
            instrumental_path,
            self.SEP_DRUMS,
            add_opt1="4",  # Mel + SCNet XL (SDR drums: 13.78)
            add_opt2="0"   # Extract directly from mixture
        )

        # Wait for job completion
        result_data = self._wait_for_completion(separation_hash)

        # Download the separated files
        files_info = result_data.get('files', [])

        # Log all files found in the response
        logger.info(f"API returned {len(files_info)} files for drums separation")
        for i, file_info in enumerate(files_info):
            filename = file_info.get('filename', '')
            url = file_info.get('url', '')
            logger.info(f"File {i+1}: filename='{filename}', url={url[:50] if url else 'None'}...")
            # Log additional file data that might help identify the files
            if 'type' in file_info:
                logger.info(f"File {i+1} type: {file_info['type']}")

        # If we have exactly 2 files in a drums/no_drums separation, and no filenames,
        # we can assume the first file is drums and the second is other
        if len(files_info) == 2 and all(not file_info.get('filename') for file_info in files_info):
            logger.info("Using positional assumption: first file is drums, second is other")

            # Try to get URLs
            if files_info[0].get('url') and files_info[1].get('url'):
                drums_path = self._download_file(files_info[0]['url'], self.temp_dir / 'drums.wav')
                other_path = self._download_file(files_info[1]['url'], self.temp_dir / 'drums_other.wav')

                # Log successful download
                if drums_path and other_path:
                    logger.info("Successfully downloaded drums and other using positional assumption")
                    return drums_path, other_path

        # Pattern matching approach
        drums_path = None
        other_path = None

        # Check each file for identifying information
        for file_info in files_info:
            url = file_info.get('url')
            if not url:
                continue

            # Check filename first
            filename = file_info.get('filename', '').lower()
            file_type = file_info.get('type', '').lower()

            # Extract name from URL if filename is empty
            if not filename and url:
                url_parts = url.split('/')
                if url_parts:
                    filename = url_parts[-1].lower()

            # Try to identify file type
            is_drums = False
            is_other = False

            # Check file_type if available
            if file_type:
                is_drums = 'drum' in file_type
                is_other = 'other' in file_type

            # Check filename patterns
            if not (is_drums or is_other) and filename:
                is_drums = 'drum' in filename
                is_other = 'other' in filename

            # Use URL as fallback
            if not (is_drums or is_other) and url:
                is_drums = 'drum' in url
                is_other = 'other' in url

            # Download the identified files
            if is_drums and not drums_path:
                drums_path = self._download_file(url, self.temp_dir / 'drums.wav')
                logger.info(f"Found drums file: url={url[:50]}...")

            elif is_other and not other_path:
                other_path = self._download_file(url, self.temp_dir / 'drums_other.wav')
                logger.info(f"Found drums_other file: url={url[:50]}...")

        # If we couldn't find the expected files, try the simplest approach - just download both
        if not drums_path or not other_path:
            if len(files_info) == 2:
                logger.info("Falling back to simple download of both files for drums and other")
                if not drums_path and files_info[0].get('url'):
                    drums_path = self._download_file(files_info[0]['url'], self.temp_dir / 'drums.wav')
                if not other_path and files_info[1].get('url'):
                    other_path = self._download_file(files_info[1]['url'], self.temp_dir / 'drums_other.wav')

        # If still missing files, raise exception
        if not drums_path or not other_path:
            missing = []
            if not drums_path:
                missing.append("drums")
            if not other_path:
                missing.append("no_drums")

            logger.error(f"Missing drum separation output files: {', '.join(missing)}")
            raise Exception(f"Failed to extract drums: output files not found")

        return drums_path, other_path

    def _extract_bass(self, no_drums_path: str) -> Tuple[str, str]:
        """
        Extract bass from the no_drums file.

        Args:
            no_drums_path: Path to audio without drums

        Returns:
            Tuple of (bass_path, no_bass_path)
        """
        logger.info(f"Extracting bass from: {no_drums_path}")

        # Start the separation job
        separation_hash = self._start_separation_job(
            no_drums_path,
            self.SEP_BASS,
            add_opt1="3",  # BS + HTDemucs + SCNet (SDR bass: 14.07)
            add_opt2="0"   # Extract directly from mixture
        )

        # Wait for job completion
        result_data = self._wait_for_completion(separation_hash)

        # Download the separated files
        files_info = result_data.get('files', [])

        # Log all files found in the response
        logger.info(f"API returned {len(files_info)} files for bass separation")
        for i, file_info in enumerate(files_info):
            filename = file_info.get('filename', '')
            url = file_info.get('url', '')
            logger.info(f"File {i+1}: filename='{filename}', url={url[:50] if url else 'None'}...")
            # Log additional file data that might help identify the files
            if 'type' in file_info:
                logger.info(f"File {i+1} type: {file_info['type']}")

        # If we have exactly 2 files in a bass/no_bass separation, and no filenames,
        # we can assume the first file is bass and the second is other
        if len(files_info) == 2 and all(not file_info.get('filename') for file_info in files_info):
            logger.info("Using positional assumption: first file is bass, second is other")

            # Try to get URLs
            if files_info[0].get('url') and files_info[1].get('url'):
                bass_path = self._download_file(files_info[0]['url'], self.temp_dir / 'bass.wav')
                other_path = self._download_file(files_info[1]['url'], self.temp_dir / 'bass_other.wav')

                # Log successful download
                if bass_path and other_path:
                    logger.info("Successfully downloaded bass and other using positional assumption")
                    return bass_path, other_path

        # Pattern matching approach
        bass_path = None
        other_path = None

        # Check each file for identifying information
        for file_info in files_info:
            url = file_info.get('url')
            if not url:
                continue

            # Check filename first
            filename = file_info.get('filename', '').lower()
            file_type = file_info.get('type', '').lower()

            # Extract name from URL if filename is empty
            if not filename and url:
                url_parts = url.split('/')
                if url_parts:
                    filename = url_parts[-1].lower()

            # Try to identify file type
            is_bass = False
            is_other = False

            # Check file_type if available
            if file_type:
                is_bass = 'bass' in file_type
                is_other = 'other' in file_type

            # Check filename patterns
            if not (is_bass or is_other) and filename:
                is_bass = 'bass' in filename
                is_other = 'other' in filename

            # Use URL as fallback
            if not (is_bass or is_other) and url:
                is_bass = 'bass' in url
                is_other = 'other' in url

            # Download the identified files
            if is_bass and not bass_path:
                bass_path = self._download_file(url, self.temp_dir / 'bass.wav')
                logger.info(f"Found bass file: url={url[:50]}...")

            elif is_other and not other_path:
                other_path = self._download_file(url, self.temp_dir / 'bass_other.wav')
                logger.info(f"Found bass_other file: url={url[:50]}...")

        # If we couldn't find the expected files, try the simplest approach - just download both
        if not bass_path or not other_path:
            if len(files_info) == 2:
                logger.info("Falling back to simple download of both files for bass and other")
                if not bass_path and files_info[0].get('url'):
                    bass_path = self._download_file(files_info[0]['url'], self.temp_dir / 'bass.wav')
                if not other_path and files_info[1].get('url'):
                    other_path = self._download_file(files_info[1]['url'], self.temp_dir / 'bass_other.wav')

        # For bass, we only need the bass file, the other file is optional
        if not bass_path:
            logger.error("Missing bass output file")
            raise Exception(f"Failed to extract bass: output file not found")

        return bass_path, other_path or no_drums_path

    def _extract_drum_components(self, drums_path: str) -> Dict[str, str]:
        """
        Extract individual drum components from the drums file.

        Args:
            drums_path: Path to the drums audio file

        Returns:
            Dictionary with paths to individual drum component files
        """
        logger.info(f"Extracting drum components from: {drums_path}")

        # Start the separation job
        separation_hash = self._start_separation_job(
            drums_path,
            self.SEP_DRUMSEP,
            add_opt1="6",  # DrumSep MelBand Roformer (4 stems)
            add_opt2="1"   # Use as is (audio must contain drums only)
        )

        # Wait for job completion
        result_data = self._wait_for_completion(separation_hash)

        # Download the separated files
        files_info = result_data.get('files', [])

        # Log all files found in the response
        logger.info(f"API returned {len(files_info)} files for drum components")
        for i, file_info in enumerate(files_info):
            filename = file_info.get('filename', '')
            url = file_info.get('url', '')
            logger.info(f"File {i+1}: filename='{filename}', url={url[:50] if url else 'None'}...")
            # Log additional file data that might help identify the files
            if 'type' in file_info:
                logger.info(f"File {i+1} type: {file_info['type']}")

        # Try to identify the drum component files
        drum_stems = {}

        # Check each file for identifying information
        for file_info in files_info:
            url = file_info.get('url')
            if not url:
                continue

            # Check filename first
            filename = file_info.get('filename', '').lower()
            file_type = file_info.get('type', '').lower()

            # Extract name from URL if filename is empty
            if not filename and url:
                url_parts = url.split('/')
                if url_parts:
                    filename = url_parts[-1].lower()

            # Try to identify the drum component type
            component_type = None

            # Check file_type if available
            if file_type:
                if 'kick' in file_type:
                    component_type = 'kick'
                elif 'snare' in file_type:
                    component_type = 'snare'
                elif 'tom' in file_type:
                    component_type = 'toms'
                # We'll handle hats separately

            # Check filename patterns
            if not component_type and filename:
                if 'kick' in filename:
                    component_type = 'kick'
                elif 'snare' in filename:
                    component_type = 'snare'
                elif 'tom' in filename:
                    component_type = 'toms'

            # Use URL as fallback
            if not component_type and url:
                if 'kick' in url:
                    component_type = 'kick'
                elif 'snare' in url:
                    component_type = 'snare'
                elif 'tom' in url:
                    component_type = 'toms'

            # Download the identified drum component
            if component_type and component_type not in drum_stems:
                output_path = self.temp_dir / f"{component_type}.wav"
                drum_stems[component_type] = self._download_file(url, output_path)
                logger.info(f"Found {component_type} file: url={url[:50]}...")

        # If we couldn't identify all required components but have the right number of files, use positional assumptions
        required_components = ['kick', 'snare', 'toms']
        missing_components = [comp for comp in required_components if comp not in drum_stems]

        if missing_components and len(files_info) >= len(required_components):
            logger.info(f"Missing components {missing_components}. Using positional assumptions.")
            # Standard ordering from MVSep is usually kick, snare, toms, cymbals
            component_mapping = {0: 'kick', 1: 'snare', 2: 'toms'}

            for i, comp_type in component_mapping.items():
                if comp_type in missing_components and i < len(files_info) and files_info[i].get('url'):
                    output_path = self.temp_dir / f"{comp_type}.wav"
                    drum_stems[comp_type] = self._download_file(files_info[i]['url'], output_path)
                    logger.info(f"Found {comp_type} file using positional assumption: url={files_info[i]['url'][:50]}...")

        # Check if we have all required components
        missing = [comp for comp in required_components if comp not in drum_stems]
        if missing:
            logger.error(f"Missing drum components: {', '.join(missing)}")
            raise Exception(f"Failed to extract drum components: missing {', '.join(missing)}")

        return drum_stems

    def _generate_hats(self, drums_path: str, drum_stems: Dict[str, str]) -> str:
        """
        Generate hats by phase-canceling other drum components from the full drums.

        Args:
            drums_path: Path to the full drums audio
            drum_stems: Dictionary with paths to individual drum component files

        Returns:
            Path to the generated hats file
        """
        logger.info("Generating hats through phase cancellation")

        try:
            # Read the drums file
            drums_data, sample_rate = sf.read(drums_path)

            # Read component files
            kick_data, _ = sf.read(drum_stems['kick'])
            snare_data, _ = sf.read(drum_stems['snare'])
            toms_data, _ = sf.read(drum_stems['toms'])

            # Make sure all arrays are the same shape
            min_length = min(len(drums_data), len(kick_data), len(snare_data), len(toms_data))
            drums_data = drums_data[:min_length]
            kick_data = kick_data[:min_length]
            snare_data = snare_data[:min_length]
            toms_data = toms_data[:min_length]

            # Sum the components
            summed_components = kick_data + snare_data + toms_data

            # Apply phase inversion without gain reduction
            inverted_components = -summed_components

            # Mix with original drums to get hats
            hats_data = drums_data + inverted_components

            # Save the hats file
            hats_path = str(self.temp_dir / 'hats.wav')
            sf.write(hats_path, hats_data, sample_rate, subtype='FLOAT')

            return hats_path

        except Exception as e:
            logger.error(f"Error generating hats: {str(e)}")
            raise

    def _generate_ee(self, original_path: str, vocal_path: str, drums_path: str, bass_path: str) -> str:
        """
        Generate EE track by phase-canceling vocals, drums, and bass from the original.

        Args:
            original_path: Path to the original audio file
            vocal_path: Path to the vocals file
            drums_path: Path to the drums file
            bass_path: Path to the bass file

        Returns:
            Path to the generated EE file
        """
        logger.info("Generating everything else (EE) through phase cancellation")

        try:
            # Read all files
            original_data, sample_rate = sf.read(original_path)
            vocal_data, _ = sf.read(vocal_path)
            drums_data, _ = sf.read(drums_path)
            bass_data, _ = sf.read(bass_path)

            # Make sure all arrays are the same shape
            min_length = min(len(original_data), len(vocal_data), len(drums_data), len(bass_data))
            original_data = original_data[:min_length]
            vocal_data = vocal_data[:min_length]
            drums_data = drums_data[:min_length]
            bass_data = bass_data[:min_length]

            # Sum the components
            summed_components = vocal_data + drums_data + bass_data

            # Apply phase inversion without gain reduction
            inverted_components = -summed_components

            # Mix with original to get EE
            ee_data = original_data + inverted_components

            # Save the EE file
            ee_path = str(self.temp_dir / 'ee.wav')
            sf.write(ee_path, ee_data, sample_rate, subtype='FLOAT')

            return ee_path


        except Exception as e:

            logger.error(f"Error generating EE: {str(e)}")

            raise
