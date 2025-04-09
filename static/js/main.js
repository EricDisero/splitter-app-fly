// Main UI Interactions for Song Splitter

// Document ready handler
document.addEventListener('DOMContentLoaded', function() {
  // File input handling
  setupFileInput();

  // HTMX events
  setupHtmxEvents();
});

// Set up file input and dropzone
function setupFileInput() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');

  if (dropzone && fileInput) {
    // Click on dropzone to trigger file input
    dropzone.addEventListener('click', function() {
      fileInput.click();
    });

    // Handle file selection
    fileInput.addEventListener('change', function() {
      if (fileInput.files.length > 0) {
        const fileName = fileInput.files[0].name;
        console.log('Selected file:', fileName);
      }
    });
  }
}

// Set up HTMX events
function setupHtmxEvents() {
  // Before any HTMX request
  document.body.addEventListener('htmx:beforeRequest', function(event) {
    const target = event.detail.elt;

    // If this is the upload form
    if (target.id === 'fileUploadForm') {
      console.log('File upload started');
    }

    // If this is the split form
    if (target.id === 'fileForm') {
      console.log('Split process started');
      if (typeof showProcessingAnimation === 'function') {
        showProcessingAnimation();
      }
    }
  });

  // After any HTMX request completes
  document.body.addEventListener('htmx:afterRequest', function(event) {
    const target = event.detail.elt;
    const responseStatus = event.detail.xhr.status;

    // If there was an error with the request
    if (responseStatus !== 200) {
      console.error('Request failed with status:', responseStatus);
    }
  });

  // After content is swapped
  document.body.addEventListener('htmx:afterSwap', function(event) {
    // If we get to the download step from the split step, hide the processing animation
    if (document.getElementById('step-download')) {
      if (typeof hideProcessingAnimation === 'function') {
        hideProcessingAnimation();
      }
    }

    // Reattach event listeners to any new elements
    setupFileInput();
  });
}

// Utility functions for drag and drop
function dragOverHandler(event) {
  event.preventDefault();
  const dropzone = document.getElementById('dropzone');
  if (dropzone) {
    dropzone.classList.add('drag-over');
  }
}

function dragLeaveHandler(event) {
  event.preventDefault();
  const dropzone = document.getElementById('dropzone');
  if (dropzone) {
    dropzone.classList.remove('drag-over');
  }
}

function dropHandler(event) {
  event.preventDefault();
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('fileInput');
  const uploadButton = document.getElementById('uploadButton');

  if (dropzone) {
    dropzone.classList.remove('drag-over');
  }

  if (fileInput && uploadButton) {
    if (event.dataTransfer.items) {
      // Use DataTransferItemList interface for modern browsers
      const dt = new DataTransfer();
      [...event.dataTransfer.items].forEach((item, i) => {
        if (item.kind === "file") {
          const file = item.getAsFile();
          console.log(`Dropped file: ${file.name}`);
          dt.items.add(file);
        }
      });

      fileInput.files = dt.files;
      uploadButton.click();
    } else {
      // Use DataTransfer interface for older browsers
      if (event.dataTransfer.files.length > 0) {
        fileInput.files = event.dataTransfer.files;
        uploadButton.click();
      }
    }
  }
}