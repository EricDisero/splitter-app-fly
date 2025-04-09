// Particle Animation System
class Particle {
    constructor(center, angle, distance, velocityMagnitude, size, alpha) {
        this.velocity = {
            x: Math.cos(angle) * velocityMagnitude,
            y: Math.sin(angle) * velocityMagnitude
        };
        this.position = {
            x: center.x + this.velocity.x * distance,
            y: center.y + this.velocity.y * distance
        };
        this.size = size;
        this.alpha = alpha;
    }

    move() {
        this.position.x += this.velocity.x;
        this.position.y += this.velocity.y;
        this.alpha -= 5; // Gradually decrease alpha to fade out particles
        this.velocity.x *= 0.8; // Decelerate
        this.velocity.y *= 0.8;
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const canvas = document.getElementById('canvas');
    if (!canvas) return; // Exit if canvas doesn't exist

    const ctx = canvas.getContext('2d');
    const phraseElement = document.getElementById('phrase');

    // Set canvas dimensions
    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    window.addEventListener('resize', resizeCanvas);
    resizeCanvas();

    // Particle system
    const particles = [];
    const maxParticles = 500;

    // Phrases list
    const phrases = [
        "Calibrating quantum entanglement parameters.",
        "Tuning the photon oscillation wavelengths.",
        "Aligning the cybernetic neural network.",
        "Processing your audio into separate tracks...",
        "Analyzing frequency spectrum bands...",
        "Isolating vocals using neural networks...",
        "Separating drum patterns from mix...",
        "Extracting bass frequencies...",
        "Filtering instrument harmonics...",
        "Applying stem separation algorithms...",
        "Preparing final audio components..."
    ];

    // Shuffle phrases
    phrases.sort(() => Math.random() - 0.5);
    let currentPhraseIndex = 0;

    // Update phrases periodically
    function updatePhrase() {
        currentPhraseIndex = (currentPhraseIndex + 1) % phrases.length;
        if (phraseElement) {
            phraseElement.textContent = phrases[currentPhraseIndex];
        }
    }

    setInterval(updatePhrase, 5000);
    updatePhrase(); // Initial phrase

    function addParticle() {
        const center = { x: canvas.width / 2, y: canvas.height / 2 };
        const angle = Math.random() * Math.PI * 2;
        const distance = Math.random() * 10 + 1;
        const velocityMagnitude = Math.random() * 5 + 15; // Consistent high initial speed
        const size = Math.random() * 2 + 1;
        const alpha = Math.random() * 100 + 100; // Start with partial opacity

        particles.push(new Particle(center, angle, distance, velocityMagnitude, size, alpha));
    }

    function animate() {
        // Clear canvas
        ctx.fillStyle = 'rgba(30, 30, 30, 1)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);

        // Add particles if needed
        if (particles.length < maxParticles) {
            addParticle();
        }

        // Update and draw particles
        for (let i = particles.length - 1; i >= 0; i--) {
            const particle = particles[i];
            particle.move();

            // Remove faded particles
            if (particle.alpha <= 0) {
                particles.splice(i, 1);
                continue;
            }

            // Draw particle
            ctx.beginPath();
            ctx.arc(particle.position.x, particle.position.y, particle.size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(116, 80, 219, ${particle.alpha / 255})`;
            ctx.fill();
        }

        requestAnimationFrame(animate);
    }

    // Start the animation only if the overlay is visible
    if (document.getElementById('processing-overlay').style.display !== 'none') {
        animate();
    }
});