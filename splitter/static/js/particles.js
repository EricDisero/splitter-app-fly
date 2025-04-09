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
        this.alpha -= 2; // Slower fade for visibility
        this.velocity.x *= 0.8; // Decelerate
        this.velocity.y *= 0.8;
    }
}

// Initialize the particle system
let canvas, ctx, particles = [], animationRunning = false;
const maxParticles = 500;

// Phrases to display
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
let shuffledPhrases = [...phrases].sort(() => Math.random() - 0.5);
let currentPhraseIndex = 0;
let phraseInterval;

// Function to set up the canvas and start animation
function setupCanvas() {
    canvas = document.getElementById('canvas');
    if (!canvas) return false;

    ctx = canvas.getContext('2d');

    // Set canvas dimensions
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    // Start with a clean slate
    particles = [];

    return true;
}

// Add new particles
function addParticle() {
    const center = { x: canvas.width / 2, y: canvas.height / 2 };
    const angle = Math.random() * Math.PI * 2;
    const distance = Math.random() * 10 + 1;
    const velocityMagnitude = Math.random() * 5 + 15;
    const size = Math.random() * 2 + 1;
    const alpha = Math.random() * 100 + 100;

    particles.push(new Particle(center, angle, distance, velocityMagnitude, size, alpha));
}

// Main animation loop
function animate() {
    if (!animationRunning) return;

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

// Update phrase text
function updatePhrase() {
    const phraseElement = document.getElementById('phrase');
    if (phraseElement) {
        currentPhraseIndex = (currentPhraseIndex + 1) % shuffledPhrases.length;
        phraseElement.textContent = shuffledPhrases[currentPhraseIndex];
    }
}

// Functions to start/stop animation
function startAnimation() {
    if (setupCanvas()) {
        animationRunning = true;

        // Start phrase rotation
        updatePhrase();
        phraseInterval = setInterval(updatePhrase, 5000);

        // Start particle animation
        animate();

        // Handle window resize
        window.addEventListener('resize', function() {
            if (animationRunning) {
                canvas.width = window.innerWidth;
                canvas.height = window.innerHeight;
            }
        });
    }
}

function stopAnimation() {
    animationRunning = false;
    if (phraseInterval) {
        clearInterval(phraseInterval);
        phraseInterval = null;
    }
}

// Listen for overlay visibility changes
const observer = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
        if (mutation.attributeName === 'style') {
            const overlay = document.getElementById('processing-overlay');
            if (overlay && overlay.style.display !== 'none') {
                startAnimation();
            } else {
                stopAnimation();
            }
        }
    });
});

// Set up the observer when the DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const overlay = document.getElementById('processing-overlay');
    if (overlay) {
        observer.observe(overlay, { attributes: true });
    }
});