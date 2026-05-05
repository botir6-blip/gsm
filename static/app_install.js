let deferredPrompt = null;

function isStandaloneMode() {
    return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
}

function installButtons() {
    return Array.from(document.querySelectorAll('#installAppButton, .install-app-button'));
}

function setInstallButtonsVisible(visible) {
    installButtons().forEach((button) => {
        button.hidden = !visible;
    });
}

window.addEventListener('beforeinstallprompt', (event) => {
    if (isStandaloneMode()) return;
    event.preventDefault();
    deferredPrompt = event;
    setInstallButtonsVisible(true);
});

window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    setInstallButtonsVisible(false);
});

document.addEventListener('DOMContentLoaded', () => {
    if (isStandaloneMode()) {
        setInstallButtonsVisible(false);
        return;
    }

    installButtons().forEach((button) => {
        button.addEventListener('click', async () => {
            if (!deferredPrompt) {
                alert('Ўрнатиш тугмаси ҳозир браузер томонидан тайёрланмаган. Chrome/Edge менюсидан “Install app” ёки “Add to Home screen” ни босинг.');
                return;
            }
            deferredPrompt.prompt();
            await deferredPrompt.userChoice;
            deferredPrompt = null;
            setInstallButtonsVisible(false);
        });
    });
});
