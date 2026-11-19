-- =====================================================================
-- database/queries.sql  (US-05)
--
-- Run:  psql -U postgres -d clinical_followup -f database/queries.sql
-- Save evidence:
--   psql -U postgres -d clinical_followup -f database/queries.sql -o docs/query-results.txt
--
-- Q1-Q3 are the three queries the brief requires. The repositories reuse
-- the same SQL (visit_repo.py, summary_repo.py), so the API returns the
-- same results. Q4-Q6 support the dashboard check and the demo.
--
-- The due window is 7 days (DUE_WINDOW_DAYS in .env). If you change it,
-- change the '7 days' intervals below too.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q1 (required): upcoming visits for a selected study
--     JOIN studies + participants + visits. Change the study code to switch study.
-- ---------------------------------------------------------------------
SELECT
    s.study_code,
    p.participant_code,
    v.visit_id,
    v.scheduled_for,
    v.visit_type,
    v.status,
    v.coordinator_code,
    CASE
        WHEN v.scheduled_for < NOW() + INTERVAL '7 days' THEN 'Due'
        ELSE NULL
    END AS due_label
FROM visits v
JOIN participants p ON p.participant_id = v.participant_id
JOIN studies s      ON s.study_id       = p.study_id
WHERE s.study_code = 'STD-SLEEP-01'
  AND v.status = 'SCHEDULED'
  AND v.scheduled_for >= NOW()
ORDER BY v.scheduled_for;


-- ---------------------------------------------------------------------
-- Q2 (required): visit counts by status (GROUP BY)
-- ---------------------------------------------------------------------
SELECT status, COUNT(*) AS visit_count
FROM visits
GROUP BY status
ORDER BY CASE status WHEN 'SCHEDULED' THEN 1 WHEN 'COMPLETED' THEN 2 WHEN 'MISSED' THEN 3 ELSE 4 END;

-- Q2b: derived labels (never stored): Due = SCHEDULED in the next 7 days,
--      Overdue = SCHEDULED with a date already past
SELECT
    COUNT(*) FILTER (WHERE status = 'SCHEDULED'
                       AND scheduled_for >= NOW()
                       AND scheduled_for <  NOW() + INTERVAL '7 days') AS due_7_days,
    COUNT(*) FILTER (WHERE status = 'SCHEDULED' AND scheduled_for < NOW()) AS overdue
FROM visits;


-- ---------------------------------------------------------------------
-- Q3 (required): summaries awaiting review
--     Successful drafts with no review row yet (LEFT JOIN ... IS NULL)
-- ---------------------------------------------------------------------
SELECT
    a.summary_id,
    a.visit_id,
    v.scheduled_for     AS visit_date,
    p.participant_code,
    s.study_code,
    a.created_at        AS drafted_at,
    'AWAITING REVIEW'   AS review_state
FROM ai_summaries a
JOIN visits v            ON v.visit_id       = a.visit_id
JOIN participants p      ON p.participant_id = v.participant_id
JOIN studies s           ON s.study_id       = p.study_id
LEFT JOIN summary_reviews r ON r.summary_id  = a.summary_id
WHERE a.generation_status = 'SUCCEEDED'
  AND r.review_id IS NULL
ORDER BY a.created_at;


-- ---------------------------------------------------------------------
-- Q4: follow-up report in one row (same fields as GET /api/reports/follow-ups)
--     Use this to prove the dashboard matches the database.
-- ---------------------------------------------------------------------
SELECT
    (SELECT COUNT(*) FROM participants WHERE consent_status = 'ACTIVE')                AS active_participants,
    COUNT(*) FILTER (WHERE v.status = 'SCHEDULED')                                      AS scheduled,
    COUNT(*) FILTER (WHERE v.status = 'SCHEDULED' AND v.scheduled_for >= NOW()
                       AND v.scheduled_for < NOW() + INTERVAL '7 days')                 AS due_7_days,
    COUNT(*) FILTER (WHERE v.status = 'SCHEDULED' AND v.scheduled_for < NOW())          AS overdue,
    COUNT(*) FILTER (WHERE v.status = 'COMPLETED')                                      AS completed,
    COUNT(*) FILTER (WHERE v.status = 'MISSED')                                         AS missed,
    COUNT(*) FILTER (WHERE v.status = 'CANCELLED')                                      AS cancelled,
    -- No completion field exists yet, so every documented action counts as open
    (SELECT COALESCE(SUM(jsonb_array_length(n.follow_up_actions)), 0) FROM visit_notes n) AS open_follow_up_actions,
    (SELECT COUNT(*) FROM ai_summaries a
       LEFT JOIN summary_reviews r ON r.summary_id = a.summary_id
      WHERE a.generation_status = 'SUCCEEDED' AND r.review_id IS NULL)                  AS awaiting_review
FROM visits v;


-- ---------------------------------------------------------------------
-- Q5: source vs AI draft vs reviewer final (proves nothing is overwritten)
-- ---------------------------------------------------------------------
SELECT
    a.summary_id,
    p.participant_code,
    (SELECT COUNT(*) FROM visit_notes n WHERE n.visit_id = a.visit_id) AS source_notes,
    a.generated_draft->>'visit_summary'                                AS ai_draft,
    r.decision,
    r.final_text                                                       AS reviewer_final,
    r.reviewer_code,
    (r.final_text IS DISTINCT FROM a.generated_draft->>'visit_summary') AS corrected_by_reviewer
FROM ai_summaries a
JOIN visits v       ON v.visit_id       = a.visit_id
JOIN participants p ON p.participant_id = v.participant_id
JOIN summary_reviews r ON r.summary_id  = a.summary_id
ORDER BY a.summary_id;


-- ---------------------------------------------------------------------
-- Q6: audit trail for one visit and its notes, drafts and reviews (time order)
--     Change the visit_id to inspect another visit.
-- ---------------------------------------------------------------------
SELECT e.created_at, e.entity_type, e.entity_id, e.action, e.actor_code, e.old_value, e.new_value
FROM audit_events e
WHERE (e.entity_type = 'visit'   AND e.entity_id = 2)
   OR (e.entity_type = 'note'    AND e.entity_id IN (SELECT note_id    FROM visit_notes  WHERE visit_id = 2))
   OR (e.entity_type = 'summary' AND e.entity_id IN (SELECT summary_id FROM ai_summaries WHERE visit_id = 2))
   OR (e.entity_type = 'review'  AND e.entity_id IN (SELECT r.review_id FROM summary_reviews r
                                                     JOIN ai_summaries a ON a.summary_id = r.summary_id
                                                     WHERE a.visit_id = 2))
ORDER BY e.created_at, e.event_id;
