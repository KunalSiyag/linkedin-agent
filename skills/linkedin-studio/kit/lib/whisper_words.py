"""Word timings for a voice file that came without them (GMI / MiniMax TTS returns audio only).
Run with the toolkit venv: .venv/bin/python lib/whisper_words.py <audio> -> JSON [{"w","start","end"}] on stdout."""
import json, os, subprocess, sys


def main():
    import numpy as np
    from faster_whisper import WhisperModel
    m = WhisperModel(os.environ.get("WHISPER_MODEL", "small.en"), device="cpu", compute_type="int8", cpu_threads=4)
    # decode with ffmpeg (like whisper_check.py), not faster-whisper's PyAV path, which breaks across av versions
    pcm = np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", sys.argv[1], "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                                       capture_output=True).stdout, np.float32).copy()
    segs, _ = m.transcribe(pcm, language="en", beam_size=5, word_timestamps=True, vad_filter=False)
    print(json.dumps([{"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
                      for s in segs for w in s.words if w.word.strip()]))


if __name__ == "__main__": main()
