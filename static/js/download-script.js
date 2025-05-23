// Simplified download management script
(function() {
    let stemData = null;
    let downloadUrlsCache = null;

    // Function to set up download handler for the main button
    function setupDownloadHandler(downloadBtn) {
        // Remove any existing listeners first to prevent multiple attachments
        const oldBtn = downloadBtn.cloneNode(true);
        downloadBtn.parentNode.replaceChild(oldBtn, downloadBtn);

        oldBtn.addEventListener('click', function(event) {
            event.preventDefault();
            downloadAllStems(this);
        });
    }

    // Download all stems function
    function downloadAllStems(button) {
        // Disable button and show loading state
        button.disabled = true;
        const originalInnerHTML = button.innerHTML;
        
        button.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="animate-spin">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
            </svg>
            Preparing downloads...
        `;

        // Get form data
        const baseName = document.getElementById('zip_file_name').value;
        const stemFilesInput = document.getElementById('stem_files');

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
        .then(response => response.json())
        .then(data => {
            if (data.status !== 'success') {
                throw new Error(data.message || 'Download failed');
            }

            // Cache the download URLs for individual downloads
            downloadUrlsCache = data.download_urls;

            // Update stem data with download URLs for individual downloads
            if (stemData && data.download_urls) {
                stemData.forEach(stem => {
                    const matchingUrl = data.download_urls.find(url => 
                        url.filename === stem.filename
                    );
                    if (matchingUrl) {
                        stem.url = matchingUrl.url;
                    }
                });
                // Re-setup handlers now that we have URLs
                setupIndividualDownloadHandlers();
            }

            button.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="animate-spin">
                    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                </svg>
                Downloading files...
            `;

            // Download all files with a small delay between each
            return downloadFiles(data.download_urls);
        })
        .then(() => {
            // Re-enable button and show success state
            button.disabled = false;
            button.innerHTML = originalInnerHTML;

            // Hide the browser download message
            hideBrowserDownloadMessage();

            // Show success message
            showDownloadComplete(button, stemData?.length || 0);

            // Add Return Home button after a delay
            setTimeout(() => {
                addReturnHomeButton(button);
            }, 2000);
        })
        .catch(error => {
            console.error('Download error:', error);
            
            // Re-enable button on error
            button.disabled = false;
            button.innerHTML = originalInnerHTML;
            
            alert('Download failed. Please try again.');
        });
    }

    // Hide the browser download message
    function hideBrowserDownloadMessage() {
        const browserMessage = document.querySelector('.mt-4.text-sm.text-center.text-gray-400');
        if (browserMessage && browserMessage.textContent.includes('Your browser will download')) {
            browserMessage.style.display = 'none';
        }
    }

    // Download individual stem
    function downloadIndividualStem(downloadUrl, filename) {
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download = filename;
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }

    // Download multiple files with delay
    function downloadFiles(downloadUrls) {
        return new Promise((resolve) => {
            downloadUrls.forEach((file, index) => {
                setTimeout(() => {
                    downloadIndividualStem(file.url, file.filename);
                    
                    // Resolve when last file download is initiated
                    if (index === downloadUrls.length - 1) {
                        setTimeout(resolve, 500);
                    }
                }, index * 1000); // 1 second delay between downloads
            });
        });
    }

    // Show download complete message
    function showDownloadComplete(button, count) {
        // Remove any existing message
        const existingMessage = button.parentNode.querySelector('.download-complete-message');
        if (existingMessage) {
            existingMessage.remove();
        }

        const messageDiv = document.createElement('div');
        messageDiv.className = 'download-complete-message';
        messageDiv.innerHTML = `
            <div class="download-success-text">All ${count} stems have been initiated for download.</div>
            <div class="download-warning-text">Please ensure all files have downloaded to your device before leaving this page. Downloads cannot be resumed after returning home or refreshing.</div>
        `;
        button.parentNode.appendChild(messageDiv);
    }

    // Add return home button
    function addReturnHomeButton(button) {
        // Check if Return Home button already exists
        const existingHomeBtn = button.parentNode.querySelector('.return-home-btn');
        if (existingHomeBtn) return;

        const homeLink = document.createElement('a');
        homeLink.className = 'btn mt-3 return-home-btn';
        homeLink.innerHTML = 'Return to Home';
        homeLink.href = '/';
        homeLink.style.display = 'inline-block';
        homeLink.style.textDecoration = 'none';

        button.parentNode.appendChild(homeLink);
    }

    // Update UI to show individual stem downloads
    function updateDownloadUI(stemFilesData) {
        try {
            stemData = JSON.parse(stemFilesData);
            const fileDetailsElement = document.querySelector('.file-details');

            if (fileDetailsElement && stemData) {
                // Build stem type list for UI
                const stemTypes = stemData.map(f => f.stem_type || 'unknown');
                const uniqueTypes = [...new Set(stemTypes)].filter(Boolean);

                // Format stem types with proper capitalization
                const formattedTypes = uniqueTypes.map(t =>
                    t === 'ee' ? 'EE' : t.charAt(0).toUpperCase() + t.slice(1)
                ).join(', ');

                // Update the details text and add individual download options
                fileDetailsElement.innerHTML = `
                    <div>Contains ${stemData.length} stems: ${formattedTypes}</div>
                    <div class="individual-downloads mt-2">
                        <div class="text-xs text-gray-500 mb-2">Individual downloads:</div>
                        <div class="stem-list">
                            ${stemData.map(stem => `
                                <div class="stem-item" data-stem-type="${stem.stem_type}" data-filename="${stem.file_name}">
                                    <span class="stem-name">${formatStemName(stem.stem_type)}</span>
                                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="download-icon" title="Download ${formatStemName(stem.stem_type)}">
                                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                        <polyline points="7 10 12 15 17 10"></polyline>
                                        <line x1="12" y1="15" x2="12" y2="3"></line>
                                    </svg>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;

                // Add click handlers for individual downloads
                setupIndividualDownloadHandlers();
            }
        } catch (e) {
            console.error('Error updating download UI:', e);
        }
    }

    // Setup click handlers for individual stem downloads
    function setupIndividualDownloadHandlers() {
        const stemItems = document.querySelectorAll('.stem-item');
        
        stemItems.forEach(item => {
            const downloadIcon = item.querySelector('.download-icon');
            const stemType = item.dataset.stemType;
            const filename = item.dataset.filename;
            
            // Remove any existing event listeners
            const newDownloadIcon = downloadIcon.cloneNode(true);
            downloadIcon.parentNode.replaceChild(newDownloadIcon, downloadIcon);
            
            newDownloadIcon.addEventListener('click', function(event) {
                event.preventDefault();
                event.stopPropagation();
                
                console.log(`Individual download clicked for: ${stemType}`);
                
                // Try to find URL from cached data first
                let downloadUrl = null;
                
                // Check if we have cached URLs from the main download
                if (downloadUrlsCache) {
                    const cachedUrl = downloadUrlsCache.find(url => 
                        url.stem_type === stemType
                    );
                    if (cachedUrl && cachedUrl.url) {
                        downloadUrl = cachedUrl.url;
                    }
                }
                
                // Check stem data
                if (!downloadUrl && stemData) {
                    const stem = stemData.find(s => s.stem_type === stemType);
                    if (stem && stem.url) {
                        downloadUrl = stem.url;
                    }
                }
                
                if (downloadUrl) {
                    console.log(`Using cached URL for ${stemType}`);
                    downloadIndividualStem(downloadUrl, filename);
                    
                    // Visual feedback
                    newDownloadIcon.style.stroke = '#10b981';
                    setTimeout(() => {
                        newDownloadIcon.style.stroke = 'currentColor';
                    }, 1000);
                } else {
                    console.log(`Fetching fresh URL for ${stemType}`);
                    // If no URL available, fetch individual download URL
                    fetchIndividualDownloadUrl(stemType, filename, newDownloadIcon);
                }
            });
        });
    }

    // Fetch individual download URL
    function fetchIndividualDownloadUrl(stemType, filename, downloadIcon) {
        const baseName = document.getElementById('zip_file_name').value;
        const stemFilesInput = document.getElementById('stem_files');
        
        // Show loading state on icon
        downloadIcon.style.stroke = '#6b7280';
        
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
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                // Find the URL for this specific stem
                const matchingUrl = data.download_urls.find(url => 
                    url.stem_type === stemType
                );
                
                if (matchingUrl && matchingUrl.url) {
                    // Cache the URLs for future use
                    if (!downloadUrlsCache) {
                        downloadUrlsCache = data.download_urls;
                    }
                    
                    // Update stem data with URL
                    if (stemData) {
                        const stem = stemData.find(s => s.stem_type === stemType);
                        if (stem) {
                            stem.url = matchingUrl.url;
                        }
                    }
                    
                    // Download the file
                    downloadIndividualStem(matchingUrl.url, filename);
                    
                    // Visual feedback
                    downloadIcon.style.stroke = '#10b981';
                    setTimeout(() => {
                        downloadIcon.style.stroke = 'currentColor';
                    }, 1000);
                } else {
                    console.error(`No URL found for ${stemType}`);
                    downloadIcon.style.stroke = '#ef4444'; // Red for error
                    setTimeout(() => {
                        downloadIcon.style.stroke = 'currentColor';
                    }, 1000);
                }
            } else {
                console.error(`Download failed: ${data.message}`);
                downloadIcon.style.stroke = '#ef4444'; // Red for error
                setTimeout(() => {
                    downloadIcon.style.stroke = 'currentColor';
                }, 1000);
            }
        })
        .catch(error => {
            console.error('Error fetching individual download URL:', error);
            downloadIcon.style.stroke = '#ef4444'; // Red for error
            setTimeout(() => {
                downloadIcon.style.stroke = 'currentColor';
            }, 1000);
        });
    }

    // Format stem name for display
    function formatStemName(stemType) {
        if (stemType === 'ee') return 'EE';
        return stemType.charAt(0).toUpperCase() + stemType.slice(1);
    }

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
                // Reset cache when new download section loads
                downloadUrlsCache = null;
                
                // Update UI to show all stem types and individual downloads
                updateDownloadUI(stemFilesInput.value);
            }
        }
    });
})();