-- ============================================================================
-- SERENSA CORRECT SCHEMA - PostgreSQL VERSION
-- ============================================================================
-- This schema correctly reflects the Django models for PostgreSQL.
-- Use this if your cPanel database is PostgreSQL instead of MySQL.
-- ============================================================================

-- ============================================================================
-- 1. CORE USER TABLE (Custom User Model) - PostgreSQL
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_user (
    id BIGSERIAL PRIMARY KEY,
    password VARCHAR(128) NOT NULL,
    last_login TIMESTAMP NULL,
    is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
    username VARCHAR(150) NOT NULL UNIQUE,
    first_name VARCHAR(150) NOT NULL DEFAULT '',
    last_name VARCHAR(150) NOT NULL DEFAULT '',
    email VARCHAR(254) NOT NULL DEFAULT '',
    is_staff BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    date_joined TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sensa_user_username ON sensa_user(username);
CREATE INDEX idx_sensa_user_is_active ON sensa_user(is_active);
CREATE INDEX idx_sensa_user_email ON sensa_user(email);

-- ============================================================================
-- 2. SHOP TABLE (with self-referencing parent_shop FK) - PostgreSQL
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_shop (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    shop_type VARCHAR(20) NOT NULL DEFAULT 'retail',
    parent_shop_id BIGINT NULL REFERENCES sensa_shop(id) ON DELETE CASCADE ON UPDATE CASCADE,
    location VARCHAR(180) NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE sensa_shop ADD CONSTRAINT unique_parent_shop_name UNIQUE (parent_shop_id, name);

CREATE INDEX idx_sensa_shop_active ON sensa_shop(active);
CREATE INDEX idx_sensa_shop_parent_shop_id ON sensa_shop(parent_shop_id);
CREATE INDEX idx_sensa_shop_created_at ON sensa_shop(created_at);

-- ============================================================================
-- 3. USER PROFILE TABLE (OneToOne with sensa_user) - PostgreSQL
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_userprofile (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE REFERENCES sensa_user(id) ON DELETE CASCADE ON UPDATE CASCADE,
    role VARCHAR(20) NOT NULL DEFAULT 'vendor',
    phone_number VARCHAR(20) NOT NULL DEFAULT ''
);

CREATE INDEX idx_sensa_userprofile_role ON sensa_userprofile(role);
CREATE INDEX idx_sensa_userprofile_phone_number ON sensa_userprofile(phone_number);

-- ============================================================================
-- 4. USER PROFILE - ASSIGNED SHOPS (ManyToMany Join Table) - PostgreSQL
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_userprofile_assigned_shops (
    id BIGSERIAL PRIMARY KEY,
    userprofile_id BIGINT NOT NULL REFERENCES sensa_userprofile(id) ON DELETE CASCADE ON UPDATE CASCADE,
    shop_id BIGINT NOT NULL REFERENCES sensa_shop(id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (userprofile_id, shop_id)
);

CREATE INDEX idx_sensa_userprofile_assigned_shops_userprofile_id ON sensa_userprofile_assigned_shops(userprofile_id);
CREATE INDEX idx_sensa_userprofile_assigned_shops_shop_id ON sensa_userprofile_assigned_shops(shop_id);

-- ============================================================================
-- 5. DAILY ENTRY TABLE (FK to shop, submitted_by user) - PostgreSQL
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_dailyentry (
    id BIGSERIAL PRIMARY KEY,
    shop_id BIGINT NOT NULL REFERENCES sensa_shop(id) ON DELETE CASCADE ON UPDATE CASCADE,
    entry_date DATE NOT NULL,
    opening_stock NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    stock_added NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    closing_stock NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    expenses NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    sales_value NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    debts NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    cash_received NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    notes TEXT NOT NULL DEFAULT '',
    submitted_by_id BIGINT NULL REFERENCES sensa_user(id) ON DELETE SET NULL ON UPDATE CASCADE,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (shop_id, entry_date)
);

CREATE INDEX idx_sensa_dailyentry_entry_date ON sensa_dailyentry(entry_date);
CREATE INDEX idx_sensa_dailyentry_shop_id ON sensa_dailyentry(shop_id);
CREATE INDEX idx_sensa_dailyentry_submitted_by_id ON sensa_dailyentry(submitted_by_id);
CREATE INDEX idx_sensa_dailyentry_updated_at ON sensa_dailyentry(updated_at);

-- ============================================================================
-- 6. JENGA API SETTINGS TABLE - PostgreSQL
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_jengaapisettings (
    id BIGSERIAL PRIMARY KEY,
    provider_name VARCHAR(50) NOT NULL DEFAULT 'Jenga',
    account_reference VARCHAR(100) NOT NULL UNIQUE,
    balance_field_path VARCHAR(255) NOT NULL DEFAULT 'balance',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sensa_jengaapisettings_account_reference ON sensa_jengaapisettings(account_reference);
CREATE INDEX idx_sensa_jengaapisettings_updated_at ON sensa_jengaapisettings(updated_at);

-- ============================================================================
-- 7. BANK BALANCE SNAPSHOT TABLE - PostgreSQL
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_bankbalancesnapshot (
    id BIGSERIAL PRIMARY KEY,
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    provider VARCHAR(50) NOT NULL DEFAULT 'Jenga',
    account_reference VARCHAR(100) NOT NULL DEFAULT '',
    balance NUMERIC(14, 2) NOT NULL DEFAULT 0.00,
    raw_response TEXT NOT NULL DEFAULT ''
);

CREATE INDEX idx_sensa_bankbalancesnapshot_fetched_at ON sensa_bankbalancesnapshot(fetched_at);
CREATE INDEX idx_sensa_bankbalancesnapshot_provider ON sensa_bankbalancesnapshot(provider);
CREATE INDEX idx_sensa_bankbalancesnapshot_account_reference ON sensa_bankbalancesnapshot(account_reference);

-- ============================================================================
-- DJANGO REQUIRED TABLES (for permissions, sessions, logging, etc.) - PostgreSQL
-- ============================================================================

-- Content Type Table (for permissions framework)
CREATE TABLE IF NOT EXISTS django_content_type (
    id SERIAL PRIMARY KEY,
    app_label VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    UNIQUE (app_label, model)
);

-- Permission Table
CREATE TABLE IF NOT EXISTS auth_permission (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    content_type_id INTEGER NOT NULL REFERENCES django_content_type(id) ON DELETE CASCADE ON UPDATE CASCADE,
    codename VARCHAR(100) NOT NULL,
    UNIQUE (content_type_id, codename)
);

-- Group Table
CREATE TABLE IF NOT EXISTS auth_group (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL UNIQUE
);

-- Group Permissions (ManyToMany)
CREATE TABLE IF NOT EXISTS auth_group_permissions (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES auth_group(id) ON DELETE CASCADE ON UPDATE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES auth_permission(id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (group_id, permission_id)
);

-- User Permissions (ManyToMany)
CREATE TABLE IF NOT EXISTS sensa_user_user_permissions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES sensa_user(id) ON DELETE CASCADE ON UPDATE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES auth_permission(id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (user_id, permission_id)
);

-- User Groups (ManyToMany)
CREATE TABLE IF NOT EXISTS sensa_user_groups (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES sensa_user(id) ON DELETE CASCADE ON UPDATE CASCADE,
    group_id INTEGER NOT NULL REFERENCES auth_group(id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (user_id, group_id)
);

-- Django Session Table
CREATE TABLE IF NOT EXISTS django_session (
    session_key VARCHAR(40) PRIMARY KEY,
    session_data TEXT NOT NULL,
    expire_date TIMESTAMP NOT NULL
);

CREATE INDEX idx_django_session_expire_date ON django_session(expire_date);

-- Django Admin Log
CREATE TABLE IF NOT EXISTS django_admin_log (
    id SERIAL PRIMARY KEY,
    action_time TIMESTAMP NOT NULL,
    user_id BIGINT NOT NULL REFERENCES sensa_user(id) ON DELETE CASCADE ON UPDATE CASCADE,
    content_type_id INTEGER NULL REFERENCES django_content_type(id) ON DELETE SET NULL ON UPDATE CASCADE,
    object_id TEXT NULL,
    object_repr VARCHAR(200) NOT NULL,
    action_flag SMALLINT NOT NULL,
    change_message TEXT NOT NULL
);

CREATE INDEX idx_django_admin_log_user_id ON django_admin_log(user_id);
CREATE INDEX idx_django_admin_log_content_type_id ON django_admin_log(content_type_id);
CREATE INDEX idx_django_admin_log_action_time ON django_admin_log(action_time);

-- ============================================================================
-- MIGRATION TRACKING TABLE - PostgreSQL
-- ============================================================================
CREATE TABLE IF NOT EXISTS django_migrations (
    id SERIAL PRIMARY KEY,
    app VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    applied TIMESTAMP NOT NULL,
    UNIQUE (app, name)
);

-- ============================================================================
-- VERIFICATION QUERIES - PostgreSQL
-- ============================================================================
-- Run these SELECT statements to verify the schema:
-- SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
-- \d sensa_userprofile;
-- SELECT constraint_name, table_name, column_name, referenced_table_name, referenced_column_name 
--   FROM information_schema.key_column_usage 
--  WHERE table_schema = 'public' AND referenced_table_name IS NOT NULL;
