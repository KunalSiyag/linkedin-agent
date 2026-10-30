"""Intelligibility check: transcribe the final mix and the clean voice with faster-whisper and compare.
Run with the toolkit venv: .venv/bin/python lib/whisper_check.py <mix> <voice> [script] -> JSON on stdout."""
import json, re, sys, os

NUM = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
       "twenty": "20", "sixty-nine": "69", "sixty": "60", "first": "1st", "number": "#"}


def norm(t):
    t = re.sub(r"\[[^\]]*\]", " ", t.lower()).replace("’", "'")
    t = re.sub(r"[^a-z0-9#' -]", " ", t)
    return [NUM.get(w, w) for w in t.replace("-", " - ").split() if w not in ("-",)]


def wer(ref, hyp):
    r, h = ref, hyp; d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1])); prev, d[j] = d[j], cur
    return d[len(h)] / max(1, len(r))


def main():
    from faster_whisper import WhisperModel
    mix, voice = sys.argv[1], sys.argv[2]; script = sys.argv[3] if len(sys.argv) > 3 else ""
    m = WhisperModel(os.environ.get("WHISPER_MODEL", "small.en"), device="cpu", compute_type="int8", cpu_threads=4)
    import subprocess, numpy as np
    def pcm(p): return np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout, np.float32).copy()
    def tr(p): return " ".join(s.text for s in m.transcribe(pcm(p), language="en", beam_size=5, vad_filter=False)[0]).strip()
    tm, tv = tr(mix), tr(voice)
    out = {"model": os.environ.get("WHISPER_MODEL", "small.en"), "mix_text": tm, "voice_text": tv,
           "wer_mix_vs_voice": round(wer(norm(tv), norm(tm)), 3)}
    if script:
        out["wer_mix_vs_script"] = round(wer(norm(script), norm(tm)), 3); out["wer_voice_vs_script"] = round(wer(norm(script), norm(tv)), 3)
    print(json.dumps(out))


if __name__ == "__main__": main()
