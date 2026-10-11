# Finovaunt profile and sign-out additions

This is a changes-only patch. It does not include or replace `frontend/src/App.tsx`, `frontend/src/styles.css`, or backend source.

Files:
- `frontend/public/profile.html` — new profile settings page; shows the signed-in username, supports password changes, and provides sign-out.
- `frontend/public/cloud-settings.html` — adds a Profile settings link; retains the existing sign-out action and cloud-account/billing UI.
- `frontend/nginx.conf` — protects `/profile.html`, routes auth endpoints to the API, and sets `absolute_redirect off` so `/` redirects to `/login.html` on the same host/port.

Merge these files into the repository root. Your frontend Dockerfile copies `frontend/public` through the Vite build (`COPY . .` then `npm run build`), so `profile.html` will be included in the generated image.

Build the frontend image with the same tag used by your local run command. Recreate only the frontend container using its existing port mapping and Docker network. Do not rebuild the API for these UI-only changes.

Pages after rebuild:
- `/login.html` — sign in
- `/profile.html` — profile/password settings
- `/cloud-settings.html` — cloud onboarding and billing
- `/dashboard/` — existing dashboard
