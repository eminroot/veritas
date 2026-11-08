-- Veritas analytics: the queries behind the README's metrics, on the star schema in
-- star_schema.sql. Money is stored in qəpik and shown in manat (÷ 100).

-- How far each project is: raised against its goal. Redirected money is counted where it is now.
SELECT p.title,
       round(p.goal_qapik / 100.0, 2)                                              AS goal_azn,
       round(sum(d.amount_qapik) FILTER (WHERE d.status <> 'claimed') / 100.0, 2)  AS raised_azn,
       round(100.0 * sum(d.amount_qapik) FILTER (WHERE d.status <> 'claimed')
             / nullif(p.goal_qapik, 0), 1)                               AS funded_pct
FROM analytics.fact_donation AS d
JOIN analytics.dim_project   AS p USING (project_key)
GROUP BY p.project_key, p.title, p.goal_qapik
ORDER BY funded_pct DESC NULLS LAST;

-- Where the money is now: in escrow, released to contractors, or back with donors.
WITH given    AS (SELECT sum(amount_qapik) AS q FROM analytics.fact_donation WHERE donation_kind <> 'redirect'),
     released AS (SELECT sum(released_qapik) AS q FROM analytics.fact_release),
     refunded AS (SELECT sum(amount_qapik) AS q FROM analytics.fact_claim WHERE action = 'refund' AND status = 'executed')
SELECT round(given.q / 100.0, 2)                                                       AS given_azn,
       round(released.q / 100.0, 2)                                                    AS released_azn,
       round(coalesce(refunded.q, 0) / 100.0, 2)                                       AS refunded_azn,
       round((given.q - coalesce(released.q, 0) - coalesce(refunded.q, 0)) / 100.0, 2) AS in_escrow_azn
FROM given, released, refunded;

-- Which evidence checks fail most often.
SELECT check_number, check_name, check_kind,
       count(*) FILTER (WHERE result <> 'not_run')                                 AS runs,
       round(100.0 * avg(is_passed::int) FILTER (WHERE result <> 'not_run'), 1)    AS pass_pct
FROM analytics.fact_evidence_check
GROUP BY check_number, check_name, check_kind
ORDER BY pass_pct, check_number;

-- How long contractors wait: evidence anchored to money paid, by country.
SELECT p.country,
       count(*)                                                                    AS payments,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY r.days_evidence_to_paid)        AS median_days,
       max(r.days_evidence_to_paid)                                                AS slowest_days
FROM analytics.fact_release AS r
JOIN analytics.dim_project  AS p USING (project_key)
WHERE r.paid_date_key <> 0
GROUP BY p.country;

-- Do donors vote? Turnout and results of closed ballots.
SELECT ballot_kind,
       count(*)                                                                    AS ballots,
       round(100.0 * sum(yes_count + no_count) / nullif(sum(eligible_count), 0), 1) AS turnout_pct,
       count(*) FILTER (WHERE is_passed)                                           AS passed,
       count(*) FILTER (WHERE is_turnout_fallback)                                 AS decided_by_fallback
FROM analytics.fact_ballot
WHERE is_passed IS NOT NULL
GROUP BY ballot_kind;

-- Giving by month and cause.
SELECT dt.year, dt.month_name, p.cause_name,
       count(DISTINCT d.donation_id)  AS payments,
       round(sum(d.amount_qapik) / 100.0, 2) AS given_azn
FROM analytics.fact_donation AS d
JOIN analytics.dim_date      AS dt USING (date_key)
JOIN analytics.dim_project   AS p  USING (project_key)
WHERE d.donation_kind <> 'redirect'
GROUP BY dt.year, dt.month, dt.month_name, p.cause_name
ORDER BY dt.year, dt.month, given_azn DESC;
