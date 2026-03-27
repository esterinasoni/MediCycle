// Shared frontend configuration for standalone static hosting.
(function configureApiUrl() {
    const queryApiUrl = new URLSearchParams(window.location.search).get('api_url');
    const savedApiUrl = window.localStorage.getItem('mc_api_url');
    const renderApiUrl = '__RENDER_BACKEND_URL__';
    const defaultApiUrl = renderApiUrl !== '__RENDER_BACKEND_URL_FALLBACK__'
        ? renderApiUrl
        : 'http://127.0.0.1:8000';

    if (queryApiUrl) {
        window.localStorage.setItem('mc_api_url', queryApiUrl);
    }

    window.API_URL = queryApiUrl || savedApiUrl || defaultApiUrl;

    console.log('='.repeat(50));
    console.log('MediCycle Frontend Loaded');
    console.log('API URL:', window.API_URL);
    console.log('Hostname:', window.location.hostname);
    console.log('='.repeat(50));
})();
