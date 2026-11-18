"""Live recordings keep making clips when the AI is missing or not answering: they clip by loudness and chat
instead. Runs against the code directly, with its own empty data folder, and starts no recording."""
import os, sys, tempfile, time
os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-liveloud-"); os.environ["DATABASE_URL"] = ""
os.environ.update(PEAKCUT_AI_KEY="", PEAKCUT_AI_KEY_FILE="", PEAKCUT_AI_MODELS="")
sys.path.insert(0, ".")
from studio import brain, config, creators, live
fails = []
def check(n, got, want=True):
    ok = want(got) if callable(want) else got == want
    print(("PASS " if ok else "FAIL ") + n + ("" if ok else f"   got {got!r}")); ok or fails.append(n)


def session(**over):
    d = tempfile.mkdtemp(prefix="pc-livejob-")
    job = {"dir": d, "clips": [], "creator": None, "title": "Test stream", "uploader": "Tester", "options": {}, "ai": {}}
    s = live.Session(job, dict(creators.DEFAULTS, **over))
    s.db = [-30.0] * 600                  # ten calm minutes...
    for t in range(400, 406):
        s.db[t] = -8.0                    # ...with a loud moment at 400 s
    s.t_done = 600.0
    s.words = [{"w": f"word{i}", "s": float(i), "e": i + 0.4} for i in range(0, 600, 2)]
    s.job["clips"] = []
    s._add_clip = lambda c: s.job["clips"].append(dict(c, made_at=time.time()))   # no rendering in a test
    return s


def last(s):
    return s.verdicts[-1]["result"] if s.verdicts else ""


# ---- no AI set up
check("the test really has no AI", config.ai_ready(), False)
s = session()
s._ai_check()
check("no AI, timed check, nothing loud: no clip", (len(s.job["clips"]), last(s).startswith("No AI")), (0, True))
s._ai_check((370, 420), "Jump: loudness +300%")
check("no AI, a jump in loudness: one clip", len(s.job["clips"]), 1)
c = s.job["clips"][0] if s.job["clips"] else {}
check("the clip covers the loud moment", c.get("start", 999) <= 400 <= c.get("end", 0), True)
check("the clip is as long as the settings allow", round(c.get("end", 0) - c.get("start", 0)), 40)
check("the clip says why it was made", "loudness" in c.get("reason", "") and "not set up" in c.get("reason", ""), True)
check("a loudness clip scores below the auto-post bar", c.get("score", 100) < creators.DEFAULTS["post_min_score"], True)
check("the decision is shown", last(s), "Clipped by loudness: the AI is not set up")
s._ai_check((380, 425), "Jump: chat +200%")
check("a second jump right after: too close, no new clip", (len(s.job["clips"]), last(s)), (1, "Too close to the last clip"))

s = session()
s._ai_check((525, 615), 'Someone said "clip"')
check("no AI, someone said clip: a clip ending just after", len(s.job["clips"]) == 1 and s.job["clips"][0]["end"] >= 590, True)

s = session(must_clip_min=15)
s.started_at = time.time() - 3600
s._ai_check()
check("no AI, 'a clip at least every' is due: the loudest moment is clipped",
      len(s.job["clips"]) == 1 and s.job["clips"][0]["start"] <= 400 <= s.job["clips"][0]["end"], True)

s = session(live_per_hour=1)
s.job["clips"] = [{"start": 10.0, "end": 50.0, "score": 60, "made_at": time.time()}]
s._add_clip = lambda c: s.job["clips"].append(dict(c, made_at=time.time()))
s._ai_check((370, 420), "Jump: loudness +300%")
check("no AI: the clips-per-hour limit still holds", (len(s.job["clips"]), "this hour already" in last(s)), (1, True))

# ---- AI set up but not answering (a retired model, no credit left...)
real_ready, real_judge = config.ai_ready, brain.judge_transcript
config.ai_ready = lambda: True
def broken(*a, **k):
    raise RuntimeError("The AI did not answer: Gemini doesn't know the model")
brain.judge_transcript = broken
s = session()
s._ai_check((370, 420), "Jump: loudness +300%")
check("AI failing, a jump: clipped by loudness instead", (len(s.job["clips"]), last(s)), (1, "Clipped by loudness: the AI did not answer"))
check("the AI error is still kept for the dashboard", "did not answer" in s.job["ai"].get("last_error", ""), True)
s._ai_check()
check("AI failing, timed check: nothing made", len(s.job["clips"]), 1)

# ---- AI working: unchanged, the AI decides
brain.judge_transcript = lambda *a, **k: ([], 10)
s = session()
s._ai_check((370, 420), "Jump: loudness +300%")
check("AI working and finds nothing: no loudness clip", (len(s.job["clips"]), last(s)), (0, "Words judge: nothing clip-worthy"))
config.ai_ready, brain.judge_transcript = real_ready, real_judge

print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
