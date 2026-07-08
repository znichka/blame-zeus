DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'zeus_app') THEN
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO zeus_app;
    END IF;
END
$$;
