CREATE TABLE tbl_process (
    id BIGSERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE tbl_sop (
    id BIGSERIAL PRIMARY KEY,
    process_id BIGINT REFERENCES tbl_process(id),

    name TEXT NOT NULL,
    purpose TEXT,
    input TEXT,
    work TEXT,
    condition TEXT,

    version INT DEFAULT 1,
    is_completed BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE tbl_sop_step (

    id BIGSERIAL PRIMARY KEY,

    sop_id BIGINT REFERENCES tbl_sop(id) ON DELETE CASCADE,

    step_order INT NOT NULL,

    step_name TEXT,

    action TEXT,

    expected_tool TEXT,

    expected_object TEXT,

    safety_check TEXT,

    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE tbl_ai_observation (

    id BIGSERIAL PRIMARY KEY,

    text_input TEXT,

    voice_text TEXT,

    image_path TEXT,

    vision_json JSONB,

    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE tbl_ai_analysis (

    id BIGSERIAL PRIMARY KEY,

    observation_id BIGINT REFERENCES tbl_ai_observation(id) ON DELETE CASCADE,

    process_name TEXT,

    process_anomaly BOOLEAN,

    safety_risk TEXT,

    sop_deviation BOOLEAN,

    final_decision TEXT,

    final_score INT,

    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE tbl_safety_log (

    id BIGSERIAL PRIMARY KEY,

    observation_id BIGINT REFERENCES tbl_ai_observation(id) ON DELETE CASCADE,

    helmet BOOLEAN,

    gloves BOOLEAN,

    vest BOOLEAN,

    risk_level TEXT,

    reason TEXT,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE EXTENSION vector;
CREATE TABLE tbl_sop_vector (
    id BIGSERIAL PRIMARY KEY,

    sop_id BIGINT REFERENCES tbl_sop(id),
    step_id BIGINT REFERENCES tbl_sop_step(id),

    content TEXT,

    embedding vector(1536),

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TYPE sensor_status AS ENUM ('ACTIVE', 'INACTIVE', 'MAINTENANCE');

CREATE TABLE sensor_info (
    sensor_id BIGSERIAL PRIMARY KEY,
    sensor_name VARCHAR(100) NOT NULL,
    location VARCHAR(100) NOT NULL,
    sensor_type VARCHAR(50) NOT NULL,
    install_date DATE NOT NULL,
    status sensor_status DEFAULT 'ACTIVE'
);
select * from sensor_data;

CREATE TABLE sensor_data (
    id SERIAL PRIMARY KEY,
    sensor_id BIGINT DEFAULT 1,
    location VARCHAR(100) NOT NULL,
    temperature INT NOT NULL,
    humidity INT,
    timestamp VARCHAR(50) NOT NULL
);

INSERT INTO sensor_info (sensor_name, location, sensor_type, install_date, status) VALUES
('BridgeA Sensor 1', 'bridgeA', 'Temperature', '2025-07-01', 'ACTIVE'),
('BridgeB Sensor 1', 'bridgeB', 'Temperature', '2025-07-02', 'ACTIVE'),
('BridgeA Sensor 2', 'bridgeA', 'Humidity', '2025-07-03', 'MAINTENANCE');

CREATE TABLE service_log (
    id BIGSERIAL PRIMARY KEY,
    log_level VARCHAR(20) NOT NULL,
    diff_score DOUBLE PRECISION,
    message TEXT,
    source VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sensor_criteria (

    id BIGSERIAL PRIMARY KEY,

    sensor_type VARCHAR(50) NOT NULL,

    location VARCHAR(100),

    min_temperature INT,
    max_temperature INT,

    min_humidity INT,
    max_humidity INT,

    description TEXT,

    created_at TIMESTAMPTZ DEFAULT now()
);


CREATE TABLE sensor_criteria (

    id BIGSERIAL PRIMARY KEY,
    location VARCHAR(100),
    sensor_type VARCHAR(50),
    min_temperature INT,
    max_temperature INT,
    min_humidity INT,
    max_humidity INT,
    updated_by VARCHAR(50),
    updated_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO sensor_criteria
(location, sensor_type, min_temperature, max_temperature, min_humidity, max_humidity, updated_by)
VALUES
('bridgeA', 'Temperature', 0, 60, NULL, NULL, 'dashboard'),

('bridgeA', 'Humidity', NULL, NULL, 20, 80, 'dashboard'),

('bridgeB', 'Temperature', 0, 70, NULL, NULL, 'dashboard'),

('bridgeB', 'Humidity', NULL, NULL, 30, 85, 'dashboard');