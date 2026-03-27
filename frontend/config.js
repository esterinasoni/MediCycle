// Environment detection
const isProduction = window.location.hostname !== 'localhost' && 
                     !window.location.hostname.includes('127.0.0.1');

// API URL - use same origin for production, localhost for dev
const API = isProduction ? window.location.origin : 'http://127.0.0.1:8000';

console.log(`?? Environment: ${isProduction ? 'Production' : 'Development'}`);
console.log(`?? API URL: ${API}`);

// Make API globally available
window.API_URL = API;
