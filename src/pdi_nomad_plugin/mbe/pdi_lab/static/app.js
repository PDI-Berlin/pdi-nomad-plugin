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
    intake: {
        title: 'Substrate Check-in',
        step: '01',
        accent: '#B78ACF',
        accentSoft: '#F2EAF7',
        url: base + '/dashboards/substrate-intake/'
    },
    processing: {
        title: 'Substrate Processing',
        step: '02',
        accent: '#A774C3',
        accentSoft: '#EDE1F4',
        url: base + '/dashboards/processing/'
    },
    experiment: {
        title: 'New MBE Experiment',
        step: '03',
        accent: '#9460B5',
        accentSoft: '#E7D7F0',
        url: base + '/dashboards/new-mbe-experiment/'
    },
    library: {
        title: 'Lab Library',
        step: '04',
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

const fullPageUrl =
    base + '/dashboards/pdi-lab/';

const nomadDashboardUrl =
    base + '/gui/v2/dashboard/pdi-lab';

const embeddedInNomad =
    window.self !== window.top;

if (embeddedInNomad) {
    modeButton.textContent = '↗ Full page';
    modeButton.title = 'Open PDI Lab full page';

    modeButton.addEventListener('click', function() {
        window.top.location.href = fullPageUrl;
    });
} else {
    modeButton.textContent = '← Back to NOMAD';
    modeButton.title = 'Return to NOMAD';

    modeButton.addEventListener('click', function() {
        window.location.href = nomadDashboardUrl;
    });
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
        frame.src = applicationUrl(key);
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

    step.textContent = config.step + ' / 04';

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
    apps[initialKey] ? initialKey : 'intake',
    false
);
