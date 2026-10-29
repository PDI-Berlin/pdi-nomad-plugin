function deploymentBase() {
    const path = window.location.pathname;
    const marker = '/dashboards/';
    const index = path.indexOf(marker);

    if (index >= 0) {
        return path.slice(0, index);
    }

    return '';
}

const base = typeof window.PDI_LAB_BASE === 'string' ? window.PDI_LAB_BASE : deploymentBase();

const apps = {
    inventory: {
        title: 'Inventory Overview', step: '01',
        accent: '#8551A7', accentSoft: '#F1E9F7',
        url: 'about:blank'
    },
    intake: {
        title: 'Substrate Check-in',
        step: '02',
        accent: '#B78ACF',
        accentSoft: '#F2EAF7',
        url: base + '/dashboards/substrate-intake/'
    },
    processing: {
        title: 'Substrate Processing',
        step: '03',
        accent: '#A774C3',
        accentSoft: '#EDE1F4',
        url: base + '/dashboards/processing/'
    },
    experiment: {
        title: 'New MBE Experiment',
        step: '04',
        accent: '#9460B5',
        accentSoft: '#E7D7F0',
        url: base + '/dashboards/new-mbe-experiment/'
    },
    library: {
        title: 'Lab Library',
        step: '05',
        accent: '#6F3F92',
        accentSoft: '#DDC5E9',
        url: base + '/dashboards/lab-library/'
    }
};

const frames = {};
const frameLoaded = {};
const appReady = {};
const pendingMessages = {};
const navigationStack = [];

document.querySelectorAll('.app-frame').forEach(function(frame) {
    const key = frame.dataset.app;
    frames[key] = frame;
    frameLoaded[key] = false;
    appReady[key] = false;

    frame.addEventListener('load', function() {
        frameLoaded[key] = true;

        if (currentApp === key) {
            loadingState.classList.add('hidden');
        }
    });
});

const loadingState = document.getElementById('loadingState');
const step = document.getElementById('workspaceStep');
const shell = document.documentElement;
const modeButton = document.getElementById('workspaceModeButton');

let currentApp = null;

// Fullscreen stays in the current browser tab.
const embeddedInNomad = window.self !== window.top;

async function toggleWorkspaceFullscreen() {
    const outerFrame = embeddedInNomad ? window.frameElement : null;
    const target = outerFrame ||
        document.querySelector('.workspace-shell');
    const ownerDocument = target.ownerDocument;

    try {
        if (ownerDocument.fullscreenElement) {
            await ownerDocument.exitFullscreen();
        } else {
            await target.requestFullscreen();
        }
    } catch (error) {
        console.error('Fullscreen unavailable:', error);
        modeButton.textContent = 'Fullscreen unavailable';
        modeButton.title =
            'The embedding page may not permit browser fullscreen.';
    }
}

modeButton.textContent = '⛶ Fullscreen';
modeButton.title = 'Toggle fullscreen in this browser tab';
modeButton.addEventListener('click', toggleWorkspaceFullscreen);

function updateFullscreenLabel() {
    const doc = window.frameElement
        ? window.frameElement.ownerDocument : document;
    modeButton.textContent = doc.fullscreenElement
        ? 'Exit fullscreen' : '⛶ Fullscreen';
}

document.addEventListener('fullscreenchange', updateFullscreenLabel);
if (window.frameElement) {
    window.frameElement.ownerDocument.addEventListener(
        'fullscreenchange', updateFullscreenLabel
    );
}

function applicationUrl(key) {
    const url = new URL(
        apps[key].url,
        window.location.href
    );

    url.searchParams.set('pdi_lab', '1');

    return url.href;
}

function ensureFrameLoaded(key) {
    const frame = frames[key];

    if (!frame) {
        return;
    }

    if (frame.dataset.started !== 'true') {
        loadingState.classList.remove('hidden');
        frame.dataset.started = 'true';
        if (key === 'inventory') {
            frame.srcdoc = window.PDI_LAB_INVENTORY_SRCDOC;
        } else {
            frame.src = applicationUrl(key);
        }
        return;
    }

    if (frameLoaded[key]) {
        loadingState.classList.add('hidden');
    } else {
        loadingState.classList.remove('hidden');
    }
}

function selectApp(key, updateHistory = true) {
    const config = apps[key];

    if (!config || !frames[key]) {
        return;
    }

    currentApp = key;

    document.querySelectorAll('.nav-item').forEach(function(button) {
        button.classList.toggle(
            'active',
            button.dataset.app === key
        );
    });

    Object.entries(frames).forEach(function(entry) {
        const frameKey = entry[0];
        const frame = entry[1];

        frame.classList.toggle(
            'active',
            frameKey === key
        );
    });

    shell.style.setProperty('--accent', config.accent);
    shell.style.setProperty('--accent-soft', config.accentSoft);

    step.textContent = config.step + ' / 05';

    ensureFrameLoaded(key);

    if (updateHistory) {
        history.replaceState(null, '', '#' + key);
    }

}


function goBack() {
    const target = navigationStack.pop();

    if (!target || !apps[target]) {
        return;
    }

    const targetReady = Boolean(appReady[target]);
    selectApp(target);
    if (targetReady) {
        postToApp(target, {type: 'pdi-lab:resume'});
    }
}


function sourceAppForWindow(sourceWindow) {
    for (const key of Object.keys(frames)) {
        if (frames[key].contentWindow === sourceWindow) {
            return key;
        }
    }

    return null;
}

function postToApp(key, message) {
    const frame = frames[key];

    if (!frame) {
        return;
    }

    if (!appReady[key]) {
        pendingMessages[key] = message;
        return;
    }

    frame.contentWindow.postMessage(
        message,
        window.location.origin
    );
}

function flushPendingMessage(key) {
    const message = pendingMessages[key];

    if (!message || !appReady[key]) {
        return;
    }

    delete pendingMessages[key];

    frames[key].contentWindow.postMessage(
        message,
        window.location.origin
    );
}

window.addEventListener('message', function(event) {
    if (event.origin !== window.location.origin) {
        return;
    }

    const sourceApp = sourceAppForWindow(event.source);

    if (!sourceApp) {
        return;
    }

    const data = event.data || {};

    if (data.type === 'pdi-lab:ready') {
        appReady[sourceApp] = true;
        flushPendingMessage(sourceApp);

        const returnTarget =
            navigationStack.length > 0
                ? navigationStack[navigationStack.length - 1]
                : null;

        frames[sourceApp].contentWindow.postMessage(
            {
                type: 'pdi-lab:return-context',
                target: returnTarget
            },
            window.location.origin
        );

        return;
    }

    if (data.type === 'pdi-lab:navigate') {
        const target = data.target;

        if (!apps[target]) {
            return;
        }

        if (sourceApp !== target) {
            navigationStack.push(sourceApp);
        }

        const targetWasReady = Boolean(appReady[target]);
        selectApp(target);

        if (data.payload) {
            postToApp(target, data.payload);
        } else if (targetWasReady) {
            postToApp(target, {
                type: 'pdi-lab:resume'
            });
        }

        return;
    }

    if (data.type === 'pdi-lab:back') {
        goBack();
    }
});

document.querySelectorAll('.nav-item').forEach(function(button) {
    button.addEventListener('click', function() {
        navigationStack.length = 0;
        const key = button.dataset.app;
        const wasReady = Boolean(appReady[key]);
        selectApp(key);
        if (wasReady) {
            postToApp(key, {
                type: 'pdi-lab:resume'
            });
        }
    });
});

const initialKey = window.location.hash.slice(1);
selectApp(
    apps[initialKey] ? initialKey : 'inventory',
    false
);



/* Fit PDI Lab to the available NOMAD dashboard viewport. */
(function () {
    function fitWorkspace() {
        try {
            const host = window.frameElement;
            if (!host) return;

            const parentWindow = window.parent;

            // Remove width caps only from ancestors of this dashboard.
            for (
                let element = host.parentElement;
                element && element !== parentWindow.document.body;
                element = element.parentElement
            ) {
                const max = parseFloat(
                    parentWindow.getComputedStyle(element).maxWidth
                );
                if (
                    Number.isFinite(max) &&
                    max >= 900 &&
                    max < parentWindow.innerWidth - 80
                ) {
                    element.style.setProperty('max-width', 'none', 'important');
                    element.style.setProperty('width', '100%', 'important');
                }
            }

            const available = Math.max(
                360,
                Math.floor(
                    parentWindow.innerHeight -
                    host.getBoundingClientRect().top - 8
                )
            );

            host.style.setProperty('height', available + 'px', 'important');
            host.style.setProperty('min-height', '0', 'important');

        } catch (error) {
            console.warn('NOMAD parent layout unavailable:', error);
        }
    }

    window.addEventListener('resize', fitWorkspace);
    try {
        window.parent.addEventListener('resize', fitWorkspace);
    } catch (error) {
        // Parent may be cross-origin.
    }
    fitWorkspace();
})();
