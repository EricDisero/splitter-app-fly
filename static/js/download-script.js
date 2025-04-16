// Improved download management script with better reliability
(function() {
    // Counter for download retries
    const MAX_RETRIES = 3;
    let retryCount = 0;

    // Store stem data between attempts
    let cachedStemData = null;

    // Define stem type categories for better UI and download ordering
    const stemCategories = {
        primary: ['vocals', 'bass', 'ee'],
        drumComponents: ['kick', 'snare', 'toms', 'hats'],
        other: [] // For any other stem types that might be added in the future
    };

    // Function to set up download handler for the button
    function setupDownloadHandler(downloadBtn) {
        // Remove any existing listeners first to prevent multiple attachments
        const oldBtn = downloadBtn.cloneNode(true);
        downloadBtn.parentNode.replaceChild(oldBtn, downloadBtn);

        oldBtn.addEventListener('click', function(event) {
            // Prevent default behavior
            event.preventDefault();

            // Disable button and show loading state
            this.disabled = true;
            const originalInnerHTML = this.innerHTML;
            this.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="animate-spin">
                    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                </svg>
                Preparing downloads...
            `;

            // Get form data
            const baseName = document.getElementById('zip_file_name').value;
            const stemFilesInput = document.getElementById('stem_files');

            // Cache the stem data for potential retries
            if (!cachedStemData) {
                cachedStemData = stemFilesInput.value;
            }

            console.log('Initiating download for:', baseName);

            // Start the download process with possible retries
            startDownloadProcess(baseName, cachedStemData, this, originalInnerHTML);
        });
    }

    // Main download process function with retry capability
    function startDownloadProcess(baseName, stemData, button, originalHTML) {
        // Check for max retries
        if (retryCount >= MAX_RETRIES) {
            alert('Download failed after multiple attempts. Please refresh the page and try again.');
            button.disabled = false;
            button.innerHTML = originalHTML;
            return;
        }

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
                stem_files: stemData
            }),
            // Increased timeout
            timeout: 60000 // 60 seconds
        })
        .then(response => {
            console.log('Download response status:', response.status);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Download data received:', data);
            if (data.status !== 'success') {
                throw new Error(data.message || 'Download failed');
            }

            // Update button text
            button.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="animate-spin">
                    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                </svg>
                Downloading files...
            `;

            // Trigger downloads
            return downloadStems(data.download_urls, baseName);
        })
        .then((downloadInfo) => {
            // If any downloads failed, retry those specifically
            if (downloadInfo.failedDownloads && downloadInfo.failedDownloads.length > 0) {
                console.warn(`${downloadInfo.failedDownloads.length} downloads failed, retrying those...`);
                return downloadStems(downloadInfo.failedDownloads, baseName, true);
            }
            return downloadInfo;
        })
        .then((downloadInfo) => {
            // Cleanup will be triggered only after all downloads are initiated
            button.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="animate-spin">
                    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                </svg>
                Finishing up...
            `;

            return new Promise((resolve) => {
                // Give time for browser to process downloads, 10 seconds
                setTimeout(() => {
                    resolve(downloadInfo);
                }, 10000);
            });
        })
        .then((downloadInfo) => {
            // Cleanup S3 files after downloads
            return cleanupS3Files(stemData)
                .then(cleanupData => ({...downloadInfo, cleanup: cleanupData}));
        })
        .then((finalResults) => {
            // Show success message with details
            const successMsg = `All ${finalResults.totalDownloads} stems have been downloaded successfully.`;
            alert(successMsg);

            // Redirect to home page after a short delay
            setTimeout(() => {
                window.location.href = '/';
            }, 1500);
        })
        .catch(error => {
            console.error('Download process error:', error);

            // Increment retry counter
            retryCount++;

            // Show retry message
            alert(`Download encountered an issue. Retrying (${retryCount}/${MAX_RETRIES})...`);

            // Retry the download process after a delay
            setTimeout(() => {
                startDownloadProcess(baseName, stemData, button, originalHTML);
            }, 3000);
        });
    }

    // Sort and download stems in a logical order with reliability improvements
    function downloadStems(downloadUrls, baseName, isRetry = false) {
        return new Promise((resolve, reject) => {
            const totalUrls = downloadUrls.length;
            console.log(`Preparing to download ${totalUrls} stems for ${baseName}${isRetry ? ' (retry attempt)' : ''}`);

            if (totalUrls === 0) {
                console.warn('No download URLs found');
                resolve({totalDownloads: 0, successfulDownloads: 0, failedDownloads: []});
                return;
            }

            // Track download results
            let successfulDownloads = 0;
            let failedDownloads = [];

            // If not retrying, categorize and order stems
            let orderedDownloads = downloadUrls;

            if (!isRetry) {
                // Categorize stems by type
                let primaryStems = [];
                let drumComponents = [];
                let otherStems = [];

                downloadUrls.forEach(file => {
                    const stemType = file.stem_type;
                    if (stemCategories.primary.includes(stemType)) {
                        primaryStems.push(file);
                    } else if (stemCategories.drumComponents.includes(stemType)) {
                        drumComponents.push(file);
                    } else {
                        otherStems.push(file);
                    }
                });

                // Sort primary stems in a logical order: vocals, bass, ee
                primaryStems.sort((a, b) => {
                    return stemCategories.primary.indexOf(a.stem_type) -
                           stemCategories.primary.indexOf(b.stem_type);
                });

                // Sort drum components in a logical order: kick, snare, toms, hats
                drumComponents.sort((a, b) => {
                    return stemCategories.drumComponents.indexOf(a.stem_type) -
                           stemCategories.drumComponents.indexOf(b.stem_type);
                });

                // Combine all stems in the desired order
                orderedDownloads = [...primaryStems, ...drumComponents, ...otherStems];
            }

            // If fewer than 3 items, download simultaneously for speed
            const useDelay = orderedDownloads.length > 3 && !isRetry;
            let downloadCount = 0;

            // Download files with an optional delay between each
            orderedDownloads.forEach((file, index) => {
                if (!file.url) {
                    console.error(`Failed to generate download URL for ${file.filename}`);
                    failedDownloads.push(file);
                    downloadCount++;

                    if (downloadCount >= totalUrls) {
                        resolve({
                            totalDownloads: totalUrls,
                            successfulDownloads,
                            failedDownloads
                        });
                    }
                    return;
                }

                // Function to perform the actual download
                const performDownload = () => {
                    try {
                        const link = document.createElement('a');
                        link.href = file.url;
                        link.download = file.filename;
                        link.style.display = 'none';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);

                        console.log(`Started download: ${file.filename} (${file.stem_type || 'unknown'})`);
                        successfulDownloads++;
                    } catch (error) {
                        console.error(`Error downloading ${file.filename}:`, error);
                        failedDownloads.push(file);
                    }

                    downloadCount++;
                    // Resolve when all downloads have been initiated
                    if (downloadCount >= totalUrls) {
                        resolve({
                            totalDownloads: totalUrls,
                            successfulDownloads,
                            failedDownloads
                        });
                    }
                };

                // Use delay or download immediately
                if (useDelay) {
                    // Stagger downloads with delay
                    setTimeout(performDownload, index * 1000); // 1 second delay between downloads
                } else {
                    // Download immediately (for retries or small batches)
                    performDownload();
                }
            });
        });
    }

    // Improved cleanup S3 files function with better error handling
    function cleanupS3Files(stemFilesJson) {
        return fetch('/cleanup_s3/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            },
            body: JSON.stringify({ stem_files: stemFilesJson }),
            // Increased timeout for cleanup
            timeout: 30000 // 30 seconds
        })
        .then(response => {
            if (!response.ok) {
                console.warn(`S3 cleanup returned status ${response.status}. Continuing anyway.`);
                return { status: 'warning', message: 'Cleanup may not have completed successfully' };
            }
            return response.json();
        })
        .then(data => {
            console.log('S3 Cleanup response:', data);
            return data;
        })
        .catch(error => {
            console.error('S3 Cleanup failed:', error);
            // Don't throw the error, as downloads have already completed
            return { status: 'error', message: 'Cleanup failed but downloads completed' };
        });
    }

    // Update the download section to show all stem types
    function updateDownloadUI(stemData) {
        try {
            const stemFiles = JSON.parse(stemData);
            const fileDetailsElement = document.querySelector('.file-details');

            if (fileDetailsElement) {
                // Build stem type list for UI
                const stemTypes = stemFiles.map(f => f.stem_type || 'unknown');
                const uniqueTypes = [...new Set(stemTypes)].filter(Boolean);

                // Format stem types with proper capitalization
                const formattedTypes = uniqueTypes.map(t =>
                    t === 'ee' ? 'EE' : t.charAt(0).toUpperCase() + t.slice(1)
                ).join(', ');

                // Update the details text
                fileDetailsElement.innerHTML = `
                    Contains ${stemFiles.length} stems: ${formattedTypes}
                `;
            }
        } catch (e) {
            console.error('Error updating download UI:', e);
        }
    }

    // Attach auto-retry logic to download errors
    window.addEventListener('error', function(e) {
        // Only check for network errors related to our download domains
        const errorSource = e.filename || '';
        if (errorSource.includes('amazonaws.com') ||
            errorSource.includes(window.location.hostname)) {
            console.warn('Download resource error detected, may retry:', e);
            // No need to do anything - the retry logic will handle this
        }
    }, true);

    // Listen for HTMX swap events to attach download handler
    document.body.addEventListener('htmx:afterSwap', (evt) => {
        // Check if the swapped content contains the download section
        const downloadSection = document.getElementById('step-download');
        if (downloadSection) {
            const downloadBtn = document.getElementById('download-btn');
            const stemFilesInput = document.getElementById('stem_files');

            if (downloadBtn) {
                console.log('Setting up download handler');
                setupDownloadHandler(downloadBtn);
            }

            if (stemFilesInput) {
                // Update UI to show all stem types
                updateDownloadUI(stemFilesInput.value);

                // Reset retry counter for each new download session
                retryCount = 0;
                cachedStemData = null;
            }
        }
    });
})();