// app/static/js/global/pastoral/podium.js
// Full path: WebChurchMan/app/static/js/global/pastoral/podium.js
// File name: podium.js
// Brief, detailed purpose:
//   Full-screen teleprompter controls for podium_view.html.
//   - Smooth auto-scroll with requestAnimationFrame
//   - Play/Pause toggle (Space key)
//   - Speed control slider + keyboard arrows (±0.1x)
//   - Real-time timer (starts on first play)
//   - Reset button / R key (scroll to top, pause, reset timer)
//   - Automatic fullscreen on load (with exit button)
//   - High performance, keyboard accessible
//   - No dependencies

document.addEventListener('DOMContentLoaded', () => {
    const container = document.getElementById('podium-container');
    const playPauseBtn = document.getElementById('play-pause-btn');
    const speedSlider = document.getElementById('speed-slider');
    const speedDisplay = document.getElementById('speed-display');
    const timer = document.getElementById('timer');
    const resetBtn = document.getElementById('reset-btn');
    const exitFullscreenBtn = document.getElementById('exit-fullscreen-btn');

    let scrolling = false;
    let speed = 1.0;
    let startTime = null;
    let animationFrame = null;

    // Main scroll loop
    function scroll() {
        if (scrolling) {
            container.scrollTop += speed * 0.8; // Base speed tuned for readability
            updateTimer();
            animationFrame = requestAnimationFrame(scroll);
        }
    }

    function updateTimer() {
        if (startTime) {
            const elapsed = Math.floor((Date.now() - startTime) / 1000);
            const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
            const secs = String(elapsed % 60).padStart(2, '0');
            timer.textContent = `${mins}:${secs}`;
        }
    }

    // Play / Pause
    playPauseBtn.addEventListener('click', () => {
        scrolling = !scrolling;
        playPauseBtn.innerHTML = scrolling ? '<i class="fas fa-pause"></i>' : '<i class="fas fa-play"></i>';

        if (scrolling) {
            if (!startTime) startTime = Date.now() - (container.scrollTop / (speed * 0.8) * 1000); // Approximate resume
            scroll();
        } else {
            cancelAnimationFrame(animationFrame);
        }
    });

    // Speed slider
    speedSlider.addEventListener('input', (e) => {
        speed = parseFloat(e.target.value);
        speedDisplay.textContent = `${speed.toFixed(1)}x`;
    });

    // Reset
    resetBtn.addEventListener('click', () => {
        container.scrollTop = 0;
        scrolling = false;
        playPauseBtn.innerHTML = '<i class="fas fa-play"></i>';
        cancelAnimationFrame(animationFrame);
        startTime = null;
        timer.textContent = '00:00';
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.code === 'Space') {
            e.preventDefault();
            playPauseBtn.click();
        } else if (e.code === 'ArrowLeft') {
            speedSlider.value = Math.max(0.3, speed - 0.1);
            speedSlider.dispatchEvent(new Event('input'));
        } else if (e.code === 'ArrowRight') {
            speedSlider.value = Math.min(3, speed + 0.1);
            speedSlider.dispatchEvent(new Event('input'));
        } else if (e.code === 'KeyR') {
            resetBtn.click();
        }
    });

    // Fullscreen
    if (container.requestFullscreen) {
        container.requestFullscreen().catch(() => {});
    }

    exitFullscreenBtn.addEventListener('click', () => {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        }
    });
});