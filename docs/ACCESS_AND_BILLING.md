# Finovaunt Login and AWS Billing Onboarding

## First login

On a fresh persistent control-plane data directory, set `FINOVAUNT_BOOTSTRAP_PASSWORD` to a unique value of at least 12 characters before startup. Finovaunt creates the `admin` account with this value; it refuses to initialize without it. The first authenticated session is restricted to the password-change screen until the password is changed. New passwords must be at least 12 characters. Passwords are stored as PBKDF2-HMAC-SHA256 hashes, not plaintext. The session uses an HttpOnly, SameSite=Strict cookie and is stored in server memory with a 12-hour server-side expiration. Credential changes revoke all active sessions. Enable `FINOVAUNT_SECURE_COOKIES=true` when deploying behind HTTPS; never expose the API publicly over plaintext HTTP.

The control-plane state is stored at `data/control-plane.json` by default. Docker Compose mounts `./data` to `/app/data` so the password and onboarded account registry persist across container recreation. Back up this file securely; it contains authentication hashes and cloud account metadata. Do not commit it.

## AWS account onboarding and billing scans

The onboarding flow currently supports AWS IAM role-based access. Supply the 12-digit AWS account ID, role ARN, and region. Configure the role trust policy to trust the AWS identity used by the Finovaunt API runtime; grant only the permissions needed for `sts:AssumeRole`, `sts:GetCallerIdentity`, and Cost Explorer `ce:GetCostAndUsage`. If the trust policy requires an external ID, enter it during onboarding and again when starting a billing scan. External IDs are not persisted.

The API runtime must itself have AWS source credentials (prefer an IAM role for the host/runtime; do not put long-lived AWS keys in the frontend). A billing scan assumes the configured role, verifies that the resulting identity belongs to the onboarded account, and reads Cost Explorer service-grouped `UnblendedCost` for the current month-to-date period. The collector follows every Cost Explorer pagination token, checks the assumed AWS account identity and rejects mixed-currency or invalid amounts. Results include the exact decimal amount as a string alongside a display-friendly rounded total. Billing periods use the first calendar day of the current UTC month through tomorrow (exclusive), so the current period is preliminary rather than a finalized invoice. Results are persisted in the local control-plane state, with a bounded history of the latest 100 scans. This flow reads billing data only; it does not mutate cloud resources or replace the existing Finovaunt optimization scan workflow. Cost Explorer must be enabled and the role must be allowed to read its data.

## Runtime storage

The API container runs read-only except for mounted artifact and control-plane data directories. Preserve both mounts when deploying. The login and onboarding layer wraps the existing dashboard; `frontend/src/App.tsx` and `frontend/src/styles.css` remain unchanged.

## Production requirements

Protect access through HTTPS, set secure cookies, and use a unique bootstrap secret. Cloud inventory and billing endpoints require a valid session. State-changing requests with untrusted Origin headers are rejected. Existing installations keep their stored password hash; the bootstrap password only applies to first initialization.
