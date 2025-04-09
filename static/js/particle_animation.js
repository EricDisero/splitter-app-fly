// All-in-one animation system with inline styling
document.addEventListener('DOMContentLoaded', function() {
  // Create the overlay elements programmatically
  const createOverlay = () => {
    // Remove any existing overlay
    const existingOverlay = document.getElementById('processing-overlay');
    if (existingOverlay) {
      return {
        overlay: existingOverlay,
        canvas: document.getElementById('animation-canvas'),
        message: document.getElementById('processing-message')
      };
    }

    // Create overlay with a subtle gradient background
    const overlay = document.createElement('div');
    overlay.id = 'processing-overlay';
    overlay.style.position = 'fixed';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    // Simple gradient in the opposite direction of main screen
    overlay.style.background = 'radial-gradient(circle at center, #0b1019 0%, #000000 100%)';
    overlay.style.zIndex = '1000';
    overlay.style.display = 'none';
    overlay.style.flexDirection = 'column';
    overlay.style.alignItems = 'center';
    overlay.style.justifyContent = 'center';
    overlay.style.overflow = 'hidden';

    // Create canvas
    const canvas = document.createElement('canvas');
    canvas.id = 'animation-canvas';
    canvas.style.position = 'absolute';
    canvas.style.top = '0';
    canvas.style.left = '0';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.zIndex = '1';
    overlay.appendChild(canvas);

    // Create title
    const title = document.createElement('div');
    title.id = 'processing-title'; // Added ID for easy access
    title.style.position = 'absolute';
    title.style.zIndex = '2';
    title.style.color = 'white';
    title.style.fontSize = '24px';
    title.style.fontWeight = 'bold';
    title.style.textAlign = 'center';
    title.style.top = '46%'; // Default position, can be adjusted
    title.style.left = '50%';
    title.style.transform = 'translate(-50%, -50%)';
    title.style.maxWidth = '80%';
    title.style.background = 'linear-gradient(to right, #a78bfa, #60a5fa)';
    title.style.webkitBackgroundClip = 'text';
    title.style.backgroundClip = 'text';
    title.style.color = 'transparent';
    title.style.fontFamily = 'Poppins, sans-serif';
    title.style.opacity = '1'; // Default opacity, can be set to 0 to hide or 1 to show
    title.textContent = 'Processing Your Audio';
    overlay.appendChild(title);

    // Create message element
    const message = document.createElement('div');
    message.id = 'processing-message';
    message.style.position = 'absolute';
    message.style.zIndex = '2';
    message.style.color = 'white';
    message.style.fontSize = '18px';
    message.style.textAlign = 'center';
    message.style.top = '50%';
    message.style.left = '50%';
    message.style.transform = 'translate(-50%, -50%)';
    message.style.maxWidth = '80%';
    message.style.fontWeight = 'bold';
    message.style.textShadow = '0 0 5px rgba(139, 92, 246, 0.5)';
    overlay.appendChild(message);

    document.body.appendChild(overlay);

    return { overlay, canvas, message };
  };

  // Variables for animation
  let particles = [];
  let animationFrame = null;
  let phraseInterval = null;

  // Messages
  const phrases = [
    "Calibrating quantum entanglement parameters.",
    "Tuning the photon oscillation wavelengths.",
    "Processing your audio into separate tracks...",
    "Analyzing frequency spectrum bands...",
    "Isolating vocals using neural networks...",
    "Separating drum patterns from mix...",
    "Extracting bass frequencies...",
    "Filtering instrument harmonics...",
    "Applying stem separation algorithms...",
    "Preparing final audio components..."
  ];

  // Shuffle array
  function shuffleArray(array) {
    const newArray = [...array];
    for (let i = newArray.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [newArray[i], newArray[j]] = [newArray[j], newArray[i]];
    }
    return newArray;
  }

  const shuffledPhrases = shuffleArray(phrases);
  let currentPhrase = 0;

  // Animation functions
  function addParticle(centerX, centerY) {
    const angle = Math.random() * Math.PI * 2;
    const distance = Math.random() * 10 + 1;
    const velocityMagnitude = Math.random() * 5 + 15;
    const size = Math.random() * 2 + 1;
    const alpha = Math.random() * 100 + 150;

    return {
      position: {
        x: centerX + Math.cos(angle) * velocityMagnitude * distance,
        y: centerY + Math.sin(angle) * velocityMagnitude * distance
      },
      velocity: {
        x: Math.cos(angle) * velocityMagnitude,
        y: Math.sin(angle) * velocityMagnitude
      },
      size,
      alpha
    };
  }

  // Animation loop function (defined outside to be accessible for cleanup)
  let animate = null;

  // Flag to prevent multiple animation instances
  let isAnimationRunning = false;

  // Public API
  window.showProcessingAnimation = function() {
    // Prevent multiple instances
    if (isAnimationRunning) return;
    isAnimationRunning = true;

    // Create or get elements
    const { overlay, canvas, message } = createOverlay();
    const ctx = canvas.getContext('2d');
    const main = document.querySelector('main');

    // Set initial message
    message.textContent = shuffledPhrases[0];
    currentPhrase = 0;

    // Setup canvas
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    particles = [];

    // Setup phrase rotation
    if (phraseInterval) clearInterval(phraseInterval);
    phraseInterval = setInterval(() => {
      currentPhrase = (currentPhrase + 1) % shuffledPhrases.length;
      message.textContent = shuffledPhrases[currentPhrase];
    }, 5000);

    // Show overlay, hide main content
    if (main) main.style.display = 'none';
    overlay.style.display = 'flex';

    // Define animation function
    animate = function() {
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;

      // Clear canvas completely (no trails)
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Add particles if needed
      if (particles.length < 500) {
        particles.push(addParticle(centerX, centerY));
      }

      // Update and draw particles
      for (let i = particles.length - 1; i >= 0; i--) {
        const particle = particles[i];

        // Move particle
        particle.position.x += particle.velocity.x;
        particle.position.y += particle.velocity.y;
        particle.alpha -= 2;
        particle.velocity.x *= 0.87;
        particle.velocity.y *= 0.87;

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

      // Request next frame
      animationFrame = requestAnimationFrame(animate);
    };

    // Start animation
    animate();

    // Handle window resize
    const handleResize = function() {
      if (overlay.style.display === 'flex') {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
      }
    };

    window.addEventListener('resize', handleResize);
  };

  window.hideProcessingAnimation = function() {
    const overlay = document.getElementById('processing-overlay');
    const main = document.querySelector('main');

    // Reset animation flag
    isAnimationRunning = false;

    // Stop animation
    if (animationFrame) {
      cancelAnimationFrame(animationFrame);
      animationFrame = null;
    }

    // Stop phrase rotation
    if (phraseInterval) {
      clearInterval(phraseInterval);
      phraseInterval = null;
    }

    // Hide overlay, show main content
    if (overlay) overlay.style.display = 'none';
    if (main) main.style.display = 'block';
  };
});