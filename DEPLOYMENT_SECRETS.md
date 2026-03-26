# GitHub Actions Secrets Configuration

To complete the dual-deploy CI/CD pipeline (Vercel + cPanel), configure the following GitHub Actions secrets:

**Repository:** `wakoTheDev/serensa`  
**Location:** 
1. Go to repository Settings → Secrets and variables → Actions
2. Click "New repository secret" for each item below

---

## Vercel Secrets (Already Configured)

- ✅ `VERCEL_TOKEN` - Your Vercel personal/team API token
- ✅ `VERCEL_ORG_ID` - Vercel organization ID
- ✅ `VERCEL_PROJECT_ID` - Vercel project ID

---

## cPanel Secrets (ADD THESE)

### Deployment Access

| Secret Name | Value | Description | Example |
|---|---|---|---|
| `CPANEL_HOST` | Server IP or hostname | Your server address | `141.95.45.75` |
| `CPANEL_PORT` | SFTP port number | Usually 1624 for cPanel | `1624` |
| `CPANEL_USER` | cPanel username | Your cPanel username | `qtmwmxfn` |
| `CPANEL_SFTP_PASSWORD` | SFTP password | Same as cPanel login | (use rotated password) |
| `CPANEL_DOMAIN` | Public domain | Domain users visit | `serensaenterprises.co.ke` |

### PostgreSQL Database Access

| Secret Name | Value | Description | Example |
|---|---|---|---|
| `CPANEL_DB_NAME` | Database name | Created in phpMyAdmin | `serensa_db` |
| `CPANEL_DB_USER` | Database user | Created in phpMyAdmin | `serensa_user` |
| `CPANEL_DB_PASSWORD` | Database password | Created in phpMyAdmin | (strong password) |
| `CPANEL_DB_HOST` | Database host | Usually localhost on same server | `localhost` |
| `CPANEL_DB_PORT` | Database port | PostgreSQL port | `5432` |

### Django Application Secrets

| Secret Name | Value | Description |
|---|---|---|
| `CPANEL_DJANGO_SECRET_KEY` | Django SECRET_KEY | Generate: `python manage.py shell -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `CPANEL_ALLOWED_HOSTS` | Comma-separated hosts | `serensaenterprises.co.ke,www.serensaenterprises.co.ke` |
| `CPANEL_CSRF_TRUSTED_ORIGINS` | Comma-separated origins | `https://serensaenterprises.co.ke,https://www.serensaenterprises.co.ke` |

---

## Setup Instructions for cPanel Database

1. **Log in to cPanel:** `https://cpanel.serensaenterprises.co.ke/`
2. **Open phpMyAdmin** (under Databases section)
3. **Create PostgreSQL Database:**
   - **Database Name:** `serensa_db` (or your choice)
   - **Database User:** `serensa_user` (or your choice)
   - **Database Password:** Create a strong password
4. **Record the details** and add them to GitHub Secrets

---

## Workflow Deployment Modes

Once secrets are configured, the pipeline supports three modes:

### 1. **Full Chain (Default - on push to main)**
- Deploy to Vercel (MongoDB)
- Wait 2 minutes for stabilization
- Verify Vercel health check
- Deploy to cPanel (PostgreSQL)
- Verify cPanel health check

### 2. **Vercel Only (Manual Trigger)**
- Go to Actions → Production Deployment Pipeline
- Click "Run workflow"
- Set deployment_mode to `vercel-only`
- Deploy only to Vercel

### 3. **cPanel Only (Manual Trigger)**
- Go to Actions → Production Deployment Pipeline
- Click "Run workflow"
- Set deployment_mode to `cpanel-only`
- Deploy only to cPanel with PostgreSQL

---

## Health Check Endpoint

The pipeline verifies deployments using:
- **Vercel:** `https://<vercel-url>/healthcheck/`
- **cPanel:** `https://serensaenterprises.co.ke/healthcheck/`

Both return `{"status": "ok", "service": "serensa"}` on success.

---

## Next Steps

1. Rotate/create secure passwords for cPanel DB and create the database via phpMyAdmin
2. Add all cPanel secrets to GitHub Actions
3. Push or trigger the workflow manually to test deployment
4. Monitor the Actions logs for any issues
5. Verify both Vercel and cPanel deployments are working

---

## Troubleshooting

**SFTP Connection Failed:**
- Verify `CPANEL_HOST`, `CPANEL_PORT`, `CPANEL_USER`, `CPANEL_SFTP_PASSWORD` are correct
- Ensure port 1624 is open (or correct port number)

**PostgreSQL Migration Failed:**
- Verify database exists and credentials are correct in phpMyAdmin
- Check PostgreSQL is running on cPanel server
- Review migration logs in Actions

**Health Check Failed:**
- Verify `/healthcheck/` endpoint is accessible
- Check Django app is running properly on cPanel
- Verify domain DNS is updated to cPanel IP

**Passenger App Not Restarting:**
- SSH into server and manually check: `ls -la /home/qtmwmxfn/public_html/tmp/restart.txt`
- CPanel Passenger should auto-restart when `tmp/restart.txt` is touched
