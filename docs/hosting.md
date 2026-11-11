# Hosting Reconcile

Public website: **https://reconcile-invoices-xi.vercel.app**.

The live deployment passed 216 database-backed tests, 11 controlled live API
checks and a browser journey. A second production deployment confirmed that the
signed-in session, original PDF, approval and order balances survived. See the
[verification summary](../ml/results/vercel-deployment/summary.json).

Application sign-in details were delivered separately to the owner. They are not
the owner's Vercel login, and no passwords are stored in this repository.

The Vercel configuration runs the website and API in a container, with a separate
background worker for invoice processing. Neon PostgreSQL stores original PDFs,
company orders, corrections and approvals, so replacing a container preserves data.

## What is configured

- `vercel.json` builds the production stage of `deploy/Dockerfile` for the app
  and one worker in Singapore (`sin1`). The worker has 2 GiB of memory.
- `reconcile.hosted` applies database migrations under a database lock, creates
  fictional demo orders and the initial approver, then starts the worker. Repeat
  startup preserves documents, existing passwords, sessions and approved amounts.
- Hosted uploads are limited to **4 MiB**, leaving room beneath Vercel's 4.5 MB
  request-body limit. The interface reads the limit from the authenticated API.
  Local development retains its 10 MiB limit.
- Secure session cookies and exact allowed website origins protect sign-in and
  staff actions. Passwords and database URLs belong in Vercel environment settings,
  never source files or the README.

## Production settings

| Name | Purpose |
|---|---|
| `DATABASE_URL` | Neon connection used by the app and processing worker. |
| `DATABASE_URL_UNPOOLED` | Direct connection used to serialize migrations safely. |
| `INITIAL_APPROVER_EMAIL` | Sign-in name for the initial approver. |
| `INITIAL_APPROVER_PASSWORD_HASH` | Argon2id password hash; the original password is kept separately. |
| `SEED_DEMO_DATA=true` | Create fictional purchase orders once for the case-study demo. |
| `SESSION_COOKIE_SECURE=true` | Send sign-in cookies over HTTPS. |
| `APP_ORIGINS` | Exact public website address; Vercel-provided deployment hosts are also recognized. |
| `MAX_UPLOAD_BYTES=4194304` | Four-MiB file limit. |
| `PORT=8000` | Container HTTP port. |

Neon was selected on its **free_v3** plan. Vercel runs on Hobby. Its current worker
quota is 420 GB-hours of provisioned memory and five active CPU-hours per month.
A continuously running 2-GiB worker uses that memory quota in about **8.75 days**;
the service stops when either quota is exhausted. Check remaining quota before a
demo. Stop or scale down the worker when it is no longer needed; longer continuous
hosting requires a different capacity arrangement. Containers and Daemons are beta
features, and Daemons run only in production.

To deploy from an authorized Vercel CLI session, link this repository to the
`reconcile-invoices` project, set the production variables, then run
`vercel deploy --prod`. The existing configuration keeps database contents across
deployments. Do not reset the database to repeat a demo; use separate order
contexts or inspect the current balance.

The owner must install/authorize the Vercel GitHub integration to enable automatic
deployments from GitHub. A direct CLI deployment works independently of that link.
