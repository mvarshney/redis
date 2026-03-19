CREATE TABLE IF NOT EXISTS players (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(50) UNIQUE NOT NULL,
    email       VARCHAR(100) UNIQUE NOT NULL,
    score       INTEGER DEFAULT 0,
    wins        INTEGER DEFAULT 0,
    losses      INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS matches (
    id          SERIAL PRIMARY KEY,
    player1_id  INTEGER REFERENCES players(id),
    player2_id  INTEGER REFERENCES players(id),
    winner_id   INTEGER REFERENCES players(id),
    status      VARCHAR(20) DEFAULT 'pending',
    created_at  TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Seed 10 players for development
INSERT INTO players (username, email, score) VALUES
    ('nova',    'nova@game.io',    4200),
    ('blaze',   'blaze@game.io',   3800),
    ('storm',   'storm@game.io',   3500),
    ('viper',   'viper@game.io',   3100),
    ('echo',    'echo@game.io',    2900),
    ('titan',   'titan@game.io',   2600),
    ('ghost',   'ghost@game.io',   2200),
    ('pixel',   'pixel@game.io',   1800),
    ('sage',    'sage@game.io',    1400),
    ('drift',   'drift@game.io',   900)
ON CONFLICT DO NOTHING;
