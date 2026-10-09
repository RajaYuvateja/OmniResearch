/**
 * OmniResearch Frontend Configuration
 * 
 * For Vercel production deployment:
 * Set window.OMNI_API_BASE to your deployed Render backend URL.
 * Example: window.OMNI_API_BASE = "https://omniresearch-backend.onrender.com";
 * 
 * When left empty (""), the frontend will automatically:
 * 1. Check for a custom URL configured in the UI Settings (stored in localStorage)
 * 2. Fallback to same-origin relative paths (for local development or monorepo hosting)
 */
window.OMNI_API_BASE = window.OMNI_API_BASE || "";
