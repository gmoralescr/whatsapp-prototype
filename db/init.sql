CREATE TABLE IF NOT EXISTS fact_interaction (
    interaction_id SERIAL PRIMARY KEY,
    customer_id    TEXT,
    visit_date     DATE,
    salesperson_id TEXT,
    desired_model  TEXT,
    intent_window_days INT,
    test_drive_flag BOOL,
    test_drive_score INT,
    stock_flag     BOOL,
    financing_flag BOOL,
    objection_codes JSONB,
    outcome        TEXT,
    competitor_brand TEXT,
    confirmed      BOOL DEFAULT FALSE
);

