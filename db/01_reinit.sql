CREATE DATABASE IF NOT EXISTS pokemon_tcg CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE pokemon_tcg;

CREATE TABLE IF NOT EXISTS cards (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    tcg VARCHAR(32) NOT NULL DEFAULT 'pokemon',
    name VARCHAR(255) NOT NULL,
    set_name VARCHAR(255) DEFAULT NULL,
    card_number VARCHAR(64) DEFAULT NULL,
    rarity VARCHAR(128) DEFAULT NULL,
    search_query VARCHAR(255) DEFAULT NULL,
    full_name VARCHAR(512) DEFAULT NULL,
    product_url VARCHAR(1024) DEFAULT NULL,
    market_price VARCHAR(32) DEFAULT NULL,
    history_total_sold INT UNSIGNED DEFAULT NULL,
    history_low_price DECIMAL(10,4) DEFAULT NULL,
    history_high_price DECIMAL(10,4) DEFAULT NULL,
    last_sold_date VARCHAR(64) DEFAULT NULL,
    last_sold_price DECIMAL(10,4) DEFAULT NULL,
    card_number_rarity VARCHAR(255) DEFAULT NULL,
    card_rarity VARCHAR(128) DEFAULT NULL,
    card_type_hp_stage VARCHAR(255) DEFAULT NULL,
    hp SMALLINT UNSIGNED DEFAULT NULL,
    stage VARCHAR(64) DEFAULT NULL,
    card_type VARCHAR(128) DEFAULT NULL,
    attacks TEXT DEFAULT NULL,
    weakness_resistance_retreat VARCHAR(255) DEFAULT NULL,
    weakness VARCHAR(64) DEFAULT NULL,
    resistance VARCHAR(64) DEFAULT NULL,
    retreat VARCHAR(32) DEFAULT NULL,
    sku_variant VARCHAR(128) DEFAULT NULL,
    sku_condition VARCHAR(128) DEFAULT NULL,
    artist VARCHAR(128) DEFAULT NULL,
    image_minio_url VARCHAR(1024) DEFAULT NULL,
    image_minio_key VARCHAR(512) DEFAULT NULL,
    scrape_error VARCHAR(512) DEFAULT NULL,
    scraped_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_name (name),
    INDEX idx_set_name (set_name),
    INDEX idx_scraped_at (scraped_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS price_history (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    card_id INT UNSIGNED NOT NULL,
    raw_json LONGTEXT NOT NULL,
    captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ph_card FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_ph_card_id (card_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS latest_sales (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    card_id INT UNSIGNED NOT NULL,
    raw_json LONGTEXT NOT NULL,
    captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ls_card FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_ls_card_id (card_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS card_images (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    card_id INT UNSIGNED NOT NULL,
    minio_bucket VARCHAR(255) NOT NULL DEFAULT 'pokemon-cards',
    minio_key VARCHAR(512) NOT NULL,
    minio_url VARCHAR(1024) DEFAULT NULL,
    image_type VARCHAR(32) DEFAULT 'front',
    original_src VARCHAR(1024) DEFAULT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ci_card FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE ON UPDATE CASCADE,
    INDEX idx_ci_card_id (card_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
