import numpy as np, soundfile as sf, subprocess
SR=48000; rng=np.random.default_rng(3)
def load(p):
    r=subprocess.run(["ffmpeg","-v","error","-i",p,"-ac","1","-ar","48000","-f","f32le","-"],capture_output=True); return np.frombuffer(r.stdout,np.float32).astype(float)
G=[load(f"interface-sounds/Audio/glitch_00{i}.ogg") for i in range(1,5)]
CN=load("sci-fi-sounds/Audio/computerNoise_000.ogg"); CN2=load("sci-fi-sounds/Audio/computerNoise_002.ogg")
def stutter(seed,dur,noise):
    r=np.random.default_rng(seed); n=int(dur*SR); x=np.zeros(n+SR); t=0
    while t<n:
        g=G[r.integers(4)]; rep=r.integers(1,4)
        for _ in range(rep):
            x[t:t+len(g)]+=g*r.uniform(.6,1); t+=len(g)+int(r.uniform(.004,.02)*SR)
        # chopped noise slice
        L=int(r.uniform(.015,.05)*SR); s=r.integers(0,len(noise)-L); x[t:t+L]+=noise[s:s+L]*r.uniform(.3,.8)*np.hanning(L)**.2; t+=L+int(r.uniform(0,.03)*SR)
    x=x[:n]; q=2**r.integers(3,6); x=np.round(x*q)/q  # light bitcrush
    x[-480:]*=np.linspace(1,0,480); return x/np.abs(x).max()*.7
sf.write("synth/glitch_stutter_a.wav",stutter(1,.45,CN),SR); sf.write("synth/glitch_stutter_b.wav",stutter(9,.7,CN2),SR)
# gated data noise
n=int(.5*SR); x=CN2[int(1*SR):int(1*SR)+n].copy(); gate=np.repeat(rng.random(n//960+1)>.35,960)[:n]; x*=gate; x=np.round(x*12)/12; x[-480:]*=np.linspace(1,0,480)
sf.write("synth/glitch_datanoise.wav",x/np.abs(x).max()*.7,SR); print("ok")
