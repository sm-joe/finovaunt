# Finovaunt cohesive frontend patch (corrected paths)

## Files
- `frontend/src/main.tsx` — actual Vite React entry point; mounts the authenticated shell.
- `frontend/src/AuthenticatedShell.tsx` — login, mandatory first password change, profile password settings, sign out, AWS onboarding, and billing scan UI.
- `frontend/src/auth.css` — styles for the added views only; does not replace `frontend/src/styles.css`.
- `frontend/nginx.conf` — serves the SPA at `/` without redirecting to `/login.html` or port 8080; proxies API routes to `api:8787`.

## Apply
Merge these paths into your existing repository. Do not replace the repository, `frontend/src/App.tsx`, `frontend/src/styles.css`, package files, API source, `.env`, `data`, or `artifacts-live`.

The previous patch had the wrong entry-point path (`frontend/main.tsx`). This corrected patch uses `frontend/src/main.tsx`.

## Important
- The frontend container must share a Docker network with the API container and resolve the API hostname `api`.
- The supplied API keeps sessions in process memory, so an API restart invalidates active sessions.
- The API's account registry does not persist the external ID; if the AWS trust policy requires one, re-enter it in the Cloud Accounts view before each scan.
- I have not been able to run your actual Docker deployment. Validate the build and login flow before relying on it in your working environment.
