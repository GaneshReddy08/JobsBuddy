"""
Station 5: WRITE PAGE  (accumulating archive)
The README is deliberately minimal: the story behind the build and nothing else.
The live board (index.html) is where the jobs live.
"""


def render_readme(jobs, profile, today):
    return """# 🌍 JobsBuddy

I'm an international student. If you are too, you know the feeling: you spend hours tailoring an application, hit submit, and *then* find out the company won't sponsor a visa. Multiply that by hundreds of applications and a ticking OPT clock, and the job hunt stops being about skill — it becomes about luck and information you don't have.

I built JobsBuddy to fix the information part. It scans thousands of tech companies every few hours and lists their US-based tech roles — no security clearance, every experience level. Roles at companies with a real visa-sponsorship history are labeled, so you can spot them first. Free, for all of us.

### 👉 [The live job board](https://siddarthareddy8.github.io/JobsBuddy/)

All the best with the hunt. You've got this. 🙌
"""
