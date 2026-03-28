-- ============================================================================
-- SCHEMA SETUP GUIDE FOR CPANEL
-- ============================================================================
-- This guide explains how to manually recreate the Serensa database schema
-- on cPanel with correct foreign key relationships.
-- ============================================================================

/*
PROBLEM IDENTIFIED:
The UserProfile table was incorrectly pointing to auth_user instead of sensa_user.
This caused: "table serensa_userprofile violates foreign key fk_serensa_userprofile_user user_id not in sensa_user table"

SOLUTION:
Completely drop all tables and recreate them using the correct schema files.

FILES PROVIDED:
1. serensa_correct_schema.sql          — For MySQL/MariaDB (recommended for cPanel)
2. serensa_correct_schema_postgresql.sql — For PostgreSQL (if using PostgreSQL)

WHICH ONE TO USE:
- Most cPanel installations use MySQL by default
- If you're unsure, use serensa_correct_schema.sql (MySQL version)
- Only use PostgreSQL version if your cPanel database is explicitly PostgreSQL
*/

-- ============================================================================
-- STEP-BY-STEP INSTRUCTIONS
-- ============================================================================

/*
STEP 1: BACKUP YOUR CURRENT DATABASE
   - cPanel > Backups > Create a Full Backup
   - OR use command: mysqldump -u cpanel_user -p database_name > backup.sql

STEP 2: IDENTIFY YOUR DATABASE DETAILS
   - Login to cPanel
   - Database: Go to MySQL® Databases to find:
     * Database name
     * Database user
     * Database password
     * Database host (usually localhost)

STEP 3: DROP OLD TABLES (WITH CAUTION!)
   - Using phpMyAdmin:
     1. Select your database
     2. Check "SELECT ALL" at bottom
     3. Use dropdown "Drop" to delete all tables
   
   - OR using command line:
     mysql -u your_db_user -p your_database_name < /path/to/serensa_correct_schema.sql

STEP 4: CREATE NEW TABLES
   
   OPTION A: Using phpMyAdmin (Recommended)
   1. Login to phpMyAdmin in cPanel
   2. Click on your database
   3. Click "Import" tab
   4. Upload the serensa_correct_schema.sql file
   5. Click "Import"
   
   OPTION B: Using SSH/Command Line
   $ ssh user@cpanel.domain.com
   $ mysql -u your_db_user -p your_database_name < serensa_correct_schema.sql
   
   When prompted for password, enter your database password.

STEP 5: VERIFY SCHEMA WAS CREATED CORRECTLY
   
   In phpMyAdmin:
   1. Navigate to your database
   2. Look in the "Tables" section - you should see:
      - sensa_user
      - sensa_shop
      - sensa_userprofile ← This is the critical one!
      - sensa_dailyentry
      - sensa_userprofile_assigned_shops
      - sensa_jengaapisettings
      - sensa_bankbalancesnapshot
      - django_* (session, migrations, admin_log, etc.)
   
   3. Click on sensa_userprofile table
   4. Go to "Structure" tab
   5. Verify the 'user_id' field shows:
      - Type: BIGINT
      - Foreign key: sensa_user(id)
      
   This is the CRITICAL check! If it still says auth_user, something went wrong.

STEP 6: DEPLOY THE FIXED CODE
   - Push the migration 0009_fix_userprofile_fk.py to your Git repo
   - The GitHub workflow will:
     1. Pull new code
     2. Run migrations (including the FK fix)
     3. Deploy to Vercel
     4. Deploy to cPanel
   
STEP 7: CREATE ADMIN ACCOUNT
   - Visit: https://your-domain.com/setup-admin/
   - Fill in admin details (username, phone number, numeric password)
   - Click "Create Admin"
   - Should succeed with no foreign key errors!

STEP 8: LOGIN
   - Visit: https://your-domain.com/login/
   - Enter username (or phone number) and password
   - Should work without issues

*/

-- ============================================================================
-- KEY SCHEMA RELATIONSHIPS
-- ============================================================================

/*
TABLE: sensa_user
  - Custom Django User model extending AbstractUser
  - Stores: id, password, username (unique), email, is_staff, is_active, etc.
  - Key: All other users reference this table

TABLE: sensa_userprofile (CRITICAL)
  - OneToOne relationship with sensa_user
  - Stores: id, user_id (FK -> sensa_user.id), role, phone_number
  - CONSTRAINT: user_id MUST reference sensa_user(id), not auth_user(id)
  
TABLE: sensa_shop
  - Parent table for business locations
  - Can reference itself (parent_shop_id) for hierarchies
  - Type can be: 'restaurant', 'retail', 'bar', 'other'

TABLE: sensa_userprofile_assigned_shops (Join Table)
  - ManyToMany relationship between UserProfile and Shop
  - Stores which vendor has access to which shops

TABLE: sensa_dailyentry
  - Daily sales/inventory entries for each shop
  - FK to sensa_shop (which shop)
  - FK to sensa_user (who submitted it)
  - Constraints: shop + entry_date must be unique

TABLE: sensa_jengaapisettings
  - Config for Jenga API integration
  - Stores account reference and balance field path

TABLE: sensa_bankbalancesnapshot
  - Historical log of bank balance fetches
  - Stores provider name, balance, raw response
*/

-- ============================================================================
-- COMMON ISSUES & SOLUTIONS
-- ============================================================================

/*
ISSUE 1: "Foreign key constraint fails"
CAUSE: Table still referencing auth_user instead of sensa_user
FIX: 
  1. Drop all tables
  2. Recreate using the correct schema file
  3. Verify using phpMyAdmin Steps 3-5 above

ISSUE 2: "User already exists" but creation failed
CAUSE: User was partially created (DB error but user insert succeeded)
FIX:
  1. Delete the user manually in phpMyAdmin
  2. Or via Django shell: User.objects.filter(username='admin').delete()
  3. Retry admin creation

ISSUE 3: "Unique constraint fails" on UserProfile
CAUSE: Multiple profiles trying to create for same user at once
FIX: This shouldn't happen with the code fixes we applied (transaction.atomic, etc.)
     If it does, the race condition is still happening. Contact support with logs.

ISSUE 4: Login works but dashboard doesn't load
CAUSE: Profile not properly linked or role not set correctly
FIX: Run this in Django shell:
     python manage.py shell
     from sensa.models import User, UserProfile
     from django.contrib.auth import get_user_model
     User = get_user_model()
     users = User.objects.all()
     for u in users:
         p, created = UserProfile.objects.get_or_create(user=u)
         if u.is_staff and p.role != 'admin':
             p.role = 'admin'
             p.save()
         print(f"User: {u.username}, Profile: {p.role}, Created: {created}")
*/

-- ============================================================================
-- QUICK REFERENCE: TABLE FIELD SIZES
-- ============================================================================

/*
varchar(150)   → Username, First/Last Name
varchar(254)   → Email
varchar(120)   → Shop Name
varchar(20)    → Phone Number, Role ('admin' or 'vendor')
varchar(180)   → Shop Location
decimal(14,2)  → All monetary amounts (sales, stock, expenses, etc.)
text           → Notes, raw responses
datetime       → Timestamps
bigint         → User/Shop IDs (large auto-increment)
int            → Permission/Group IDs (standard Django size)
boolean        → Flags (is_active, is_staff, is_superuser, active)
*/

-- ============================================================================
-- FINAL CHECKLIST
-- ============================================================================

/*
Before you consider this done:
☐ Backup current database
☐ Identified database name, user, password, host
☐ Dropped old tables
☐ Imported correct schema using phpMyAdmin or MySQL CLI
☐ Verified in phpMyAdmin that sensa_userprofile has FK to sensa_user (NOT auth_user)
☐ Deployed code with migration 0009_fix_userprofile_fk
☐ Successfully created admin account without FK errors
☐ Successfully logged in with admin account
☐ Admin can access admin dashboard
*/

-- ============================================================================
-- SUPPORT
-- ============================================================================

/*
If you encounter issues:

1. Check phpMyAdmin > Your Database > sensa_userprofile
   - Go to Structure tab
   - Verify user_id FK points to sensa_user, not auth_user
   
2. Check cPanel logs:
   - cPanel > Errors in /home/user/public_html/error_log
   
3. Enable DEBUG in settings.py:
   - Add: DEBUG = True (temporarily, only for testing)
   - Django will show detailed error messages
   
4. Run health check:
   - Visit: https://your-domain.com/healthcheck/
   - Should return JSON with "status": "ok"
*/

