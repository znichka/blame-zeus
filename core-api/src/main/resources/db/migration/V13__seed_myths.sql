-- Hand-curated (C5). Five canonical myths + their myth_participants.
-- myths has no source_id FK (ADR-007 / IMPLEMENTATION_PLAN.md §3) — a myth is not
-- attributed to a single source; source attribution lives on relationships/variant_claims
-- and narrative_chunks. Participants reference entities by name via subquery so this
-- migration stays decoupled from V10's SERIAL ids; every name below exists in
-- V10__seed_entities.sql (Perseus/Medusa/Eris were hand-added ahead of this file — see
-- DEVIATIONS.md #DEV-045). id/name lookups use ON CONFLICT DO NOTHING for re-apply safety.

INSERT INTO myths (title, location, summary) VALUES
    ('The Judgment of Paris',
     'Mount Ida, near Troy',
     'At the wedding of Peleus and Thetis, Eris casts a golden apple "for the fairest," setting Hera, Athena, and Aphrodite against one another. Zeus sends the goddesses to the Trojan prince Paris, who awards the apple to Aphrodite in exchange for the most beautiful mortal woman — Helen — precipitating the Trojan War.'),
    ('The Abduction of Persephone',
     'Nysa / the Underworld',
     'Hades carries Persephone down to the Underworld to be his queen. Her mother Demeter, goddess of the harvest, blights the earth in grief until Zeus intervenes; the compromise by which Persephone spends part of the year below and part above becomes the myth of the seasons.'),
    ('Perseus and Medusa',
     'Seriphos / the far West',
     'Sent by Polydectes to fetch the head of the Gorgon Medusa, Perseus — son of Danae — slays her with the aid of Athena, using her reflection to avoid her petrifying gaze, and bears the head back as a weapon.'),
    ('Odysseus and the Cyclops Polyphemus',
     'The island of the Cyclopes',
     'Trapped in the cave of the Cyclops Polyphemus, Odysseus blinds the man-eating giant and escapes beneath his sheep. Because Polyphemus is a son of Poseidon, the sea-god pursues Odysseus with storms for the rest of his long voyage home.'),
    ('The Transformation of Arachne',
     'Lydia',
     'The mortal weaver Arachne boasts she surpasses Athena at the loom and challenges the goddess to a contest. Enraged by Arachne''s flawless but impious tapestry, Athena transforms her into a spider, condemned to weave forever.')
ON CONFLICT DO NOTHING;

-- Participants: role describes the entity's function in the myth (not a schema enum).
INSERT INTO myth_participants (myth_id, entity_id, role)
SELECT m.id, e.id, v.role
FROM (VALUES
    -- The Judgment of Paris
    ('The Judgment of Paris', 'Eris',      'instigator'),
    ('The Judgment of Paris', 'Paris',     'judge'),
    ('The Judgment of Paris', 'Aphrodite', 'contestant (winner)'),
    ('The Judgment of Paris', 'Hera',      'contestant'),
    ('The Judgment of Paris', 'Athena',    'contestant'),
    ('The Judgment of Paris', 'Zeus',      'arbiter'),
    ('The Judgment of Paris', 'Peleus',    'bridegroom'),
    ('The Judgment of Paris', 'Thetis',    'bride'),
    -- The Abduction of Persephone
    ('The Abduction of Persephone', 'Hades',      'abductor'),
    ('The Abduction of Persephone', 'Persephone', 'victim'),
    ('The Abduction of Persephone', 'Demeter',    'grieving mother'),
    ('The Abduction of Persephone', 'Zeus',       'arbiter'),
    -- Perseus and Medusa
    ('Perseus and Medusa', 'Perseus',    'hero'),
    ('Perseus and Medusa', 'Medusa',     'monster (slain)'),
    ('Perseus and Medusa', 'Athena',     'divine helper'),
    ('Perseus and Medusa', 'Polydectes', 'quest-giver'),
    ('Perseus and Medusa', 'Danae',      'mother'),
    -- Odysseus and the Cyclops Polyphemus
    ('Odysseus and the Cyclops Polyphemus', 'Odysseus',   'hero'),
    ('Odysseus and the Cyclops Polyphemus', 'Polyphemus', 'antagonist'),
    ('Odysseus and the Cyclops Polyphemus', 'Poseidon',   'divine pursuer'),
    -- The Transformation of Arachne
    ('The Transformation of Arachne', 'Arachne', 'mortal challenger'),
    ('The Transformation of Arachne', 'Athena',  'goddess')
) AS v(myth_title, entity_name, role)
JOIN myths m    ON m.title = v.myth_title
JOIN entities e ON e.name  = v.entity_name
ON CONFLICT (myth_id, entity_id) DO NOTHING;
