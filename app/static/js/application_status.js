document.addEventListener('submit', async event => {
    const form = event.target;
    if (!form.matches('[data-status-update]')) return;
    event.preventDefault();

    const button = form.querySelector('button[type="submit"]');
    const message = form.querySelector('.status-message');
    const token = form.elements.csrf_token.value;
    button.disabled = true;
    message.textContent = 'Saving...';

    try {
        const response = await fetch(form.dataset.endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': token
            },
            body: JSON.stringify({
                status: form.elements.status.value,
                note: form.elements.note.value,
                csrf_token: token
            })
        });
        const result = await response.json();
        if (!response.ok) {
            message.textContent = result.error || 'The status could not be updated.';
            button.disabled = false;
            return;
        }
        window.location.reload();
    } catch {
        message.textContent = 'The status could not be updated. Check your connection and try again.';
        button.disabled = false;
    }
});