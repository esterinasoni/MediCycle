// Environment detection
const isProduction = window.location.hostname !== 'localhost' && 
                     !window.location.hostname.includes('127.0.0.1') &&
                     !window.location.hostname.includes('192.168');

// API URL - use same origin for production, localhost for dev
if (!window.API_URL) {
    window.API_URL = isProduction ? window.location.origin : 'http://127.0.0.1:8000';
}

console.log('=' . repeat(50));
console.log('MediCycle Frontend Loaded');
console.log('Environment:', isProduction ? 'PRODUCTION' : 'DEVELOPMENT');
console.log('API URL:', window.API_URL);
console.log('Hostname:', window.location.hostname);
console.log('=' . repeat(50));