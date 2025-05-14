// Improved download management script without client-side cleanup
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
            // Update button with success state
            button.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                    <polyline points="22 4 12 14.01 9 11.01"></polyline>
                </svg>
                Downloads Complete
            `;

            // Show success message
            const successMsg = `All ${downloadInfo.totalDownloads} stems have been downloaded.`;

            // Add a message below the button
            const messageDiv = document.createElement('div');
            messageDiv.className = 'mt-3 text-sm text-center text-gray-400';
            messageDiv.textContent = successMsg;
            button.parentNode.appendChild(messageDiv);

            // Add a Return Home link after a delay
            setTimeout(() => {
                const homeLink = document.createElement('a');
                homeLink.className = 'btn mt-3';
                homeLink.innerHTML = 'Return to Home';
                homeLink.href = '/';
                homeLink.style.display = 'inline-block';
                homeLink.style.textDecoration = 'none';

                button.parentNode.appendChild(homeLink);
            }, 2000);

            return downloadInfo;
        })
        .catch(error => {
            console.error('Download process error:', error);

            // Increment retry counter
            retryCount++;

            // Show retry message
            const errorMsg = `Download encountered an issue. Retrying (${retryCount}/${MAX_RETRIES})...`;
            console.warn(errorMsg);

            // Update button to show retry state
            button.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M23 4v6h-6"></path>
                    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                </svg>
                Retrying...
            `;

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
            const useDelay = true; // Always stagger downloads
            const delayMs = 3000; // 3 seconds between downloads
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
                    setTimeout(performDownload, index * delayMs);
                } else {
                    // Download immediately (for retries or small batches)
                    performDownload();
                }
            });
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