document.addEventListener('DOMContentLoaded', function () {
    var splitButton = document.getElementById('splitBtn');
    var fileName = document.getElementById('audioName');
    splitButton.addEventListener('click', function() {
        fetch("/split/", {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({'file_name': fileName.textContent})
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
        console.log('isFinished:', data.isFinished);   
        document.getElementById('top_label').textContent = data.isFinished == 'exist' ? "FOLDER WITH SONG NAME EXISTS": "ERROR OCCURRED";
        document.getElementById('beforeUploading').style.display = 'block';
        document.getElementById('afterUploading').style.display = 'none';
        })
        .catch(error => console.error('Error:', error))
    });

    var importButton = document.getElementById('browseBtn');
    importButton.addEventListener('click', function() {
        var input = document.createElement('input');
        input.type = 'file';
        input.accept = 'audio/*'
        input.onchange = function (e) {
            var file = e.target.files[0];
            console.log('Selected file:', file);
            uploadFile(file);
        };
        input.click();
    })
    }
)


function uploadFile(file) {
    var formData = new FormData();
    formData.append('file', file);
    fetch('/upload_audio/', {
        method: 'POST',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: formData,
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        console.log('File uploaded successfully', data);
        document.getElementById('audioName').innerHTML = file.name;
        document.getElementById('afterUploading').style.display = 'block';
        document.getElementById('beforeUploading').style.display = 'none';
    })
}


function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = cookies[i].trim();
            // Check if the cookie contains the CSRF token
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}