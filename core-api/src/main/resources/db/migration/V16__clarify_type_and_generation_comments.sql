-- DEV-054: text-to-SQL used `parent.generation IS NOT NULL` as a "divine parent" proxy, but the
-- seed populates entities.generation on only 2 of ~1,969 rows (Cronus, Metis) — so the filter
-- matched nothing. The V8_3 comment ("Divine generation number… NULL for mortals and heroes")
-- actively invited that misread. Divinity actually lives in entities.type. Re-comment both columns
-- so SchemaIntrospector surfaces the correct signal to TextToSqlAgent (same channel as V15/DEV-047).

COMMENT ON COLUMN entities.type IS
    'Coarse kind of the figure and the signal for divinity: the divine types are primordial, titan, olympian, other_god. Heroes, mortals, and monsters are NOT divine. For "divine"/"god"/"deity" questions filter on type (e.g. type IN (''primordial'',''titan'',''olympian'',''other_god'')), never on generation.';
COMMENT ON COLUMN entities.generation IS
    'Sparsely populated (mostly NULL, even for gods) — do NOT use as a divinity test or assume NULL means mortal. Use type for divinity instead.';
