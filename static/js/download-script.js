// Download management script
(function() {
    // Function to set up download handler for a specific button
    function setupDownloadHandler(downloadBtn) {
        // Remove any existing listeners first to prevent multiple attachments
        const oldBtn = downloadBtn.cloneNode(true);
        downloadBtn.parentNode.replaceChild(oldBtn, downloadBtn);

        oldBtn.addEventListener('click', function(event) {
            // Prevent any default behavior
            event.preventDefault();

            // Disable button and show loading state
            this.disabled = true;
            const originalInnerHTML = this.innerHTML;
            this.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="animate-spin">
                    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                </svg>
                Downloading...
            `;

            // Get form data
            const baseName = document.getElementById('zip_file_name').value;
            const stemFilesInput = document.getElementById('stem_files');

            console.log('Initiating download for:', baseName);

            // Fetch download URLs
            fetch('/download/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                },
                body: new URLSearchParams({
                    base_name: baseName,
                    stem_files: stemFilesInput.value
                })
            })
            .then(response => {
                console.log('Download response:', response);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('Download data:', data);
                if (data.status !== 'success') {
                    throw new Error(data.message || 'Download failed');
                }

                // Trigger downloads
                return downloadStems(data.download_urls, baseName);
            })
            .then((totalUrls) => {
                // Cleanup will be triggered immediately after last download is initiated
                return new Promise((resolve) => {
                    // Add a small buffer to ensure download events are processed 3 seconds
                    setTimeout(() => {
                        resolve(totalUrls);
                    }, 3000);
                });
            })
            .then((totalUrls) => {
                // Cleanup S3 files after downloads
                return cleanupS3Files(stemFilesInput.value);
            })
            .then(() => {
                // Redirect to home page
                window.location.href = '/';
            })
            .catch(error => {
                console.error('Download process error:', error);
                alert('An error occurred during download. Please try again.');
            })
            .finally(() => {
                // Restore button state
                this.disabled = false;
                this.innerHTML = originalInnerHTML;
            });
        });
    }

    // Download stems function
    function downloadStems(downloadUrls, baseName) {
        return new Promise((resolve, reject) => {
            console.log(`Preparing to download ${downloadUrls.length} stems for ${baseName}`);

            let downloadCount = 0;
            const totalUrls = downloadUrls.length;

            if (totalUrls === 0) {
                console.warn('No download URLs found');
                resolve(0);
                return;
            }

            // Shuffle download order to mitigate potential first-file issues
            const shuffledUrls = [...downloadUrls].sort(() => Math.random() - 0.5);

            shuffledUrls.forEach((file, index) => {
                if (!file.url) {
                    console.error(`Failed to generate download URL for ${file.filename}`);
                    downloadCount++;
                    return;
                }

                // Stagger downloads
                setTimeout(() => {
                    try {
                        const link = document.createElement('a');
                        link.href = file.url;
                        link.download = file.filename;
                        link.style.display = 'none';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);

                        console.log(`Started download: ${file.filename}`);
                    } catch (error) {
                        console.error(`Error downloading ${file.filename}:`, error);
                    }

                    downloadCount++;
                    // Resolve when all downloads have been initiated
                    if (downloadCount >= totalUrls) {
                        resolve(totalUrls);
                    }
                }, index * 1000); // Slight delay between downloads 1 second
            });
        });
    }

    // Cleanup S3 files function
    function cleanupS3Files(stemFilesJson) {
        return fetch('/cleanup_s3/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: JSON.stringify({ stem_files: stemFilesJson })
        })
        .then(response => response.json())
        .then(data => {
            console.log('S3 Cleanup response:', data);
        })
        .catch(error => {
            console.error('S3 Cleanup failed:', error);
        });
    }

    // Listen for HTMX swap events to attach download handler
    document.body.addEventListener('htmx:afterSwap', (evt) => {
        // Check if the swapped content contains the download section
        const downloadSection = document.getElementById('step-download');
        if (downloadSection) {
            const downloadBtn = document.getElementById('download-btn');
            if (downloadBtn) {
                console.log('Setting up download handler');
                setupDownloadHandler(downloadBtn);
            }
        }
    });
})();