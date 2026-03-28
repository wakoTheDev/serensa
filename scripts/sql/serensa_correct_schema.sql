-- ============================================================================
-- SERENSA CORRECT SCHEMA
-- ============================================================================
-- This schema correctly reflects the Django models with proper foreign keys,
-- constraints, and indexes. Use this to manually recreate tables on cPanel.
-- ============================================================================

-- ============================================================================
-- 1. CORE USER TABLE (Custom User Model)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_user (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    password VARCHAR(128) NOT NULL,
    last_login DATETIME NULL,
    is_superuser BOOLEAN NOT NULL DEFAULT 0,
    username VARCHAR(150) NOT NULL UNIQUE,
    first_name VARCHAR(150) NOT NULL DEFAULT '',
    last_name VARCHAR(150) NOT NULL DEFAULT '',
    email VARCHAR(254) NOT NULL DEFAULT '',
    is_staff BOOLEAN NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    date_joined DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_username (username),
    INDEX idx_is_active (is_active),
    INDEX idx_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 2. SHOP TABLE (with self-referencing parent_shop FK)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_shop (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(120) NOT NULL,
    shop_type VARCHAR(20) NOT NULL DEFAULT 'retail',
    parent_shop_id BIGINT NULL,
    location VARCHAR(180) NOT NULL DEFAULT '',
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_sensa_shop_parent FOREIGN KEY (parent_shop_id)
        REFERENCES sensa_shop(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT unique_parent_shop_name UNIQUE (name, parent_shop_id),
    
    INDEX idx_active (active),
    INDEX idx_parent_shop_id (parent_shop_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 3. USER PROFILE TABLE (OneToOne with sensa_user)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_userprofile (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL UNIQUE,
    role VARCHAR(20) NOT NULL DEFAULT 'vendor',
    phone_number VARCHAR(20) NOT NULL DEFAULT '',
    
    CONSTRAINT fk_sensa_userprofile_user FOREIGN KEY (user_id)
        REFERENCES sensa_user(id) ON DELETE CASCADE ON UPDATE CASCADE,
    
    INDEX idx_role (role),
    INDEX idx_phone_number (phone_number),
    UNIQUE KEY unique_user_profile (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 4. USER PROFILE - ASSIGNED SHOPS (ManyToMany Join Table)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_userprofile_assigned_shops (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    userprofile_id BIGINT NOT NULL,
    shop_id BIGINT NOT NULL,
    
    CONSTRAINT fk_userprofile FOREIGN KEY (userprofile_id)
        REFERENCES sensa_userprofile(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_shop FOREIGN KEY (shop_id)
        REFERENCES sensa_shop(id) ON DELETE CASCADE ON UPDATE CASCADE,
    
    UNIQUE KEY unique_assignment (userprofile_id, shop_id),
    INDEX idx_userprofile_id (userprofile_id),
    INDEX idx_shop_id (shop_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 5. DAILY ENTRY TABLE (FK to shop, submitted_by user)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_dailyentry (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    shop_id BIGINT NOT NULL,
    entry_date DATE NOT NULL,
    opening_stock DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    stock_added DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    closing_stock DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    expenses DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    sales_value DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    debts DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    cash_received DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    notes LONGTEXT NOT NULL DEFAULT '',
    submitted_by_id BIGINT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_dailyentry_shop FOREIGN KEY (shop_id)
        REFERENCES sensa_shop(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_dailyentry_submitted_by FOREIGN KEY (submitted_by_id)
        REFERENCES sensa_user(id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT unique_shop_entry_date UNIQUE (shop_id, entry_date),
    
    INDEX idx_entry_date (entry_date),
    INDEX idx_shop_id (shop_id),
    INDEX idx_submitted_by_id (submitted_by_id),
    INDEX idx_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 6. JENGA API SETTINGS TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_jengaapisettings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    provider_name VARCHAR(50) NOT NULL DEFAULT 'Jenga',
    account_reference VARCHAR(100) NOT NULL UNIQUE,
    balance_field_path VARCHAR(255) NOT NULL DEFAULT 'balance',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_account_reference (account_reference),
    INDEX idx_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- 7. BANK BALANCE SNAPSHOT TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS sensa_bankbalancesnapshot (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    fetched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    provider VARCHAR(50) NOT NULL DEFAULT 'Jenga',
    account_reference VARCHAR(100) NOT NULL DEFAULT '',
    balance DECIMAL(14, 2) NOT NULL DEFAULT 0.00,
    raw_response LONGTEXT NOT NULL DEFAULT '',
    
    INDEX idx_fetched_at (fetched_at),
    INDEX idx_provider (provider),
    INDEX idx_account_reference (account_reference)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- DJANGO REQUIRED TABLES (for permissions, sessions, logging, etc.)
-- ============================================================================

-- Content Type Table (for permissions framework)
CREATE TABLE IF NOT EXISTS django_content_type (
    id INT PRIMARY KEY AUTO_INCREMENT,
    app_label VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    UNIQUE KEY unique_content_type (app_label, model)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Permission Table
CREATE TABLE IF NOT EXISTS auth_permission (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    content_type_id INT NOT NULL,
    codename VARCHAR(100) NOT NULL,
    
    CONSTRAINT fk_permission_content_type FOREIGN KEY (content_type_id)
        REFERENCES django_content_type(id) ON DELETE CASCADE,
    UNIQUE KEY unique_permission (content_type_id, codename)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Group Table
CREATE TABLE IF NOT EXISTS auth_group (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(150) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Group Permissions (ManyToMany)
CREATE TABLE IF NOT EXISTS auth_group_permissions (
    id INT PRIMARY KEY AUTO_INCREMENT,
    group_id INT NOT NULL,
    permission_id INT NOT NULL,
    
    CONSTRAINT fk_group FOREIGN KEY (group_id)
        REFERENCES auth_group(id) ON DELETE CASCADE,
    CONSTRAINT fk_permission FOREIGN KEY (permission_id)
        REFERENCES auth_permission(id) ON DELETE CASCADE,
    UNIQUE KEY unique_group_permission (group_id, permission_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- User Permissions (ManyToMany)
CREATE TABLE IF NOT EXISTS sensa_user_user_permissions (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    permission_id INT NOT NULL,
    
    CONSTRAINT fk_user FOREIGN KEY (user_id)
        REFERENCES sensa_user(id) ON DELETE CASCADE,
    CONSTRAINT fk_perm FOREIGN KEY (permission_id)
        REFERENCES auth_permission(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_permission (user_id, permission_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- User Groups (ManyToMany)
CREATE TABLE IF NOT EXISTS sensa_user_groups (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    group_id INT NOT NULL,
    
    CONSTRAINT fk_user_groups FOREIGN KEY (user_id)
        REFERENCES sensa_user(id) ON DELETE CASCADE,
    CONSTRAINT fk_group_groups FOREIGN KEY (group_id)
        REFERENCES auth_group(id) ON DELETE CASCADE,
    UNIQUE KEY unique_user_group (user_id, group_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Django Session Table
CREATE TABLE IF NOT EXISTS django_session (
    session_key VARCHAR(40) PRIMARY KEY,
    session_data LONGTEXT NOT NULL,
    expire_date DATETIME NOT NULL,
    
    INDEX idx_expire_date (expire_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Django Admin Log
CREATE TABLE IF NOT EXISTS django_admin_log (
    id INT PRIMARY KEY AUTO_INCREMENT,
    action_time DATETIME NOT NULL,
    user_id BIGINT NOT NULL,
    content_type_id INT NULL,
    object_id LONGTEXT NULL,
    object_repr VARCHAR(200) NOT NULL,
    action_flag SMALLINT NOT NULL,
    change_message LONGTEXT NOT NULL,
    
    CONSTRAINT fk_admin_user FOREIGN KEY (user_id)
        REFERENCES sensa_user(id) ON DELETE CASCADE,
    CONSTRAINT fk_admin_content_type FOREIGN KEY (content_type_id)
        REFERENCES django_content_type(id) ON DELETE SET NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_content_type_id (content_type_id),
    INDEX idx_action_time (action_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- MIGRATION TRACKING TABLE
-- ============================================================================
CREATE TABLE IF NOT EXISTS django_migrations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    app VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    applied DATETIME NOT NULL,
    UNIQUE KEY unique_migration (app, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VERIFICATION SCRIPT
-- ============================================================================
-- Run these SELECT statements to verify the schema:
-- SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() ORDER BY table_name;
-- SHOW CREATE TABLE sensa_userprofile;
-- SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME 
--   FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE 
--  WHERE TABLE_SCHEMA = DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL;
