"""
Station 4a: MATCH SCORE
Scores each job 0-100 against the resume skills (rules-based, no AI).
Score = how many of MY skills the job mentions + small role/sponsor boosts.
"""


def score_job(job, profile):
    blob = f"{job['title']} {job['description']}".lower()
    skills = profile["skills"]

    hit = [s for s in skills if s in blob]
    # de-dupe near-identical skill tokens for the display list
    seen, matched = set(), []
    for s in hit:
        key = s.replace(".", "").replace("-", "")
        if key not in seen:
            seen.add(key)
            matched.append(s)

    # base: proportion of a "good match" (cap at ~10 skills = strong)
    base = min(len(matched), 10) / 10 * 80      # up to 80 pts from skills
    role_boost = 12 if any(r in job["title"].lower()
                           for r in ["ai", "full stack", "fullstack", "data", "software"]) else 0
    sponsor_boost = 8 if job.get("sponsors_visa") else 0

    score = int(min(100, base + role_boost + sponsor_boost))
    job["match_score"] = score
    job["matched_skills"] = matched[:6]
    return job


def score_all(jobs, profile):
    return [score_job(j, profile) for j in jobs]
