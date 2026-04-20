CREATE TABLE IF NOT EXISTS Activities (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    date DATE NOT NULL,
    steps INT NOT NULL DEFAULT 0,
    calories_burned INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (user_id > 0),
    CHECK (steps >= 0),
    CHECK (calories_burned >= 0)
);
