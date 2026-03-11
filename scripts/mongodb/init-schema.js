// MongoDB schema bootstrap for Serensa domain models.
// Run with: mongosh "<MONGODB_URI>" scripts/mongodb/init-schema.js

const dbName = process.env.MONGODB_NAME || "serensa";
const targetDb = db.getSiblingDB(dbName);

function ensureCollection(name, validator) {
  const exists = targetDb.getCollectionInfos({ name }).length > 0;
  if (!exists) {
    targetDb.createCollection(name, { validator });
    print(`Created collection: ${name}`);
  } else {
    targetDb.runCommand({ collMod: name, validator });
    print(`Updated validator: ${name}`);
  }
}

ensureCollection("sensa_shop", {
  $jsonSchema: {
    bsonType: "object",
    required: ["name", "active", "created_at"],
    properties: {
      id: { bsonType: ["long", "int"] },
      name: { bsonType: "string", minLength: 1, maxLength: 120 },
      location: { bsonType: "string", maxLength: 180 },
      active: { bsonType: "bool" },
      created_at: { bsonType: "date" }
    }
  }
});

ensureCollection("sensa_userprofile", {
  $jsonSchema: {
    bsonType: "object",
    required: ["user_id", "role", "phone_number"],
    properties: {
      id: { bsonType: ["long", "int"] },
      user_id: { bsonType: ["long", "int"] },
      role: { enum: ["admin", "vendor"] },
      phone_number: { bsonType: "string", maxLength: 20 }
    }
  }
});

// Many-to-many join table for UserProfile.assigned_shops.
ensureCollection("sensa_userprofile_assigned_shops", {
  $jsonSchema: {
    bsonType: "object",
    required: ["userprofile_id", "shop_id"],
    properties: {
      id: { bsonType: ["long", "int"] },
      userprofile_id: { bsonType: ["long", "int"] },
      shop_id: { bsonType: ["long", "int"] }
    }
  }
});

ensureCollection("sensa_dailyentry", {
  $jsonSchema: {
    bsonType: "object",
    required: [
      "shop_id",
      "entry_date",
      "opening_stock",
      "stock_added",
      "expenses",
      "debts",
      "closing_stock",
      "cash_received",
      "updated_at"
    ],
    properties: {
      id: { bsonType: ["long", "int"] },
      shop_id: { bsonType: ["long", "int"] },
      entry_date: { bsonType: "date" },
      opening_stock: { bsonType: ["decimal", "double", "string"] },
      stock_added: { bsonType: ["decimal", "double", "string"] },
      expenses: { bsonType: ["decimal", "double", "string"] },
      debts: { bsonType: ["decimal", "double", "string"] },
      closing_stock: { bsonType: ["decimal", "double", "string"] },
      cash_received: { bsonType: ["decimal", "double", "string"] },
      notes: { bsonType: "string" },
      submitted_by_id: { bsonType: ["long", "int", "null"] },
      updated_at: { bsonType: "date" }
    }
  }
});

ensureCollection("sensa_bankbalancesnapshot", {
  $jsonSchema: {
    bsonType: "object",
    required: ["fetched_at", "provider", "account_reference", "balance"],
    properties: {
      id: { bsonType: ["long", "int"] },
      fetched_at: { bsonType: "date" },
      provider: { bsonType: "string", maxLength: 50 },
      account_reference: { bsonType: "string", maxLength: 100 },
      balance: { bsonType: ["decimal", "double", "string"] },
      raw_response: { bsonType: "string" }
    }
  }
});

// Indexes from Django model constraints and query usage.
targetDb.sensa_shop.createIndex({ name: 1 }, { unique: true, name: "uniq_sensa_shop_name" });
targetDb.sensa_shop.createIndex({ active: 1 }, { name: "idx_sensa_shop_active" });

targetDb.sensa_userprofile.createIndex({ user_id: 1 }, { unique: true, name: "uniq_sensa_userprofile_user" });
targetDb.sensa_userprofile.createIndex({ phone_number: 1 }, { name: "idx_sensa_userprofile_phone" });

targetDb.sensa_userprofile_assigned_shops.createIndex(
  { userprofile_id: 1, shop_id: 1 },
  { unique: true, name: "uniq_profile_shop" }
);

targetDb.sensa_dailyentry.createIndex(
  { shop_id: 1, entry_date: 1 },
  { unique: true, name: "unique_shop_entry_date" }
);
targetDb.sensa_dailyentry.createIndex({ entry_date: -1, updated_at: -1 }, { name: "idx_dailyentry_ordering" });

targetDb.sensa_bankbalancesnapshot.createIndex({ fetched_at: -1 }, { name: "idx_snapshot_fetched_desc" });

print("Serensa MongoDB schema bootstrap complete.");
