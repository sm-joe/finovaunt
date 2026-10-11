# Finovaunt login and cloud onboarding

- Open `http://localhost:4173/` to reach the login page. First login is `admin` / `admin` and requires a password change (minimum 12 characters).
- After login, the existing dashboard is served at `/dashboard/` without changing `App.tsx` or `styles.css`.
- Open `/cloud-settings.html` to onboard an AWS account and run a read-only Cost Explorer billing scan.
- Onboarding requires the 12-digit account ID, IAM role ARN, and region. The role trust policy must permit the API's AWS identity to call `sts:AssumeRole`. The assumed role should have Cost Explorer read permissions. An optional external ID is supplied again at scan time and is not persisted.
- Login/account state is persisted in `./data/control-plane.json`; scan artifacts remain in `./artifacts-live`. Do not delete either directory to troubleshoot login.
- The dashboard API is still the same projection API; its existing API paths are protected at Nginx by the session check, except health and sync status.
- This integration keeps `frontend/src/App.tsx` and `frontend/src/styles.css` unchanged.
